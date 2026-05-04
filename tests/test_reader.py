import zipfile

import pytest
import rdflib

from rdf_dump_reader.reader import InvalidURIError, RDFDumpReader


def test_package_exports_public_api():
    from rdf_dump_reader import RDFDumpReader as PackageReader
    from rdf_dump_reader import Record

    assert PackageReader is RDFDumpReader
    assert Record.__name__ == "Record"


def _write_zip(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        items = entries.items() if isinstance(entries, dict) else ((name, None) for name in entries)
        for name, content in items:
            archive.writestr(name, _valid_rdf(name) if content is None else content)


def _valid_rdf(name):
    subject = name.replace(" ", "_")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <rdf:Description rdf:about="http://example.org/{subject}">
    <dc:title>{name}</dc:title>
  </rdf:Description>
</rdf:RDF>
"""


INVALID_RDF = "<rdf:RDF><rdf:Description></rdf:RDF>"

INVALID_URI_RDF = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <rdf:Description rdf:about="http://example.org/invalid uri">
    <dc:title>Invalid URI</dc:title>
  </rdf:Description>
</rdf:RDF>
"""


def test_reader_instantiation(tmp_path):
    reader = RDFDumpReader(tmp_path)
    assert reader is not None


def test_invalid_path_raises(tmp_path):
    missing_path = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        RDFDumpReader(missing_path)


def test_non_directory_path_raises(tmp_path):
    file_path = tmp_path / "dump.txt"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        RDFDumpReader(file_path)


@pytest.mark.parametrize(
    ("option_name", "option_value"),
    [
        ("on_parse_error", "continue"),
        ("invalid_uri_policy", "rewrite"),
    ],
)
def test_invalid_option_values_raise(tmp_path, option_name, option_value):
    with pytest.raises(ValueError):
        RDFDumpReader(tmp_path, **{option_name: option_value})


def test_zip_discovery_and_ordering(tmp_path):
    for filename in ["beta.zip", "alpha.ZIP", "001.zip", "gamma.Zip"]:
        (tmp_path / filename).write_text("", encoding="utf-8")

    reader = RDFDumpReader(tmp_path)

    assert [path.name for path in reader._zip_paths] == [
        "001.zip",
        "alpha.ZIP",
        "beta.zip",
        "gamma.Zip",
    ]


def test_zip_discovery_ignores_non_zip_files_and_nested_zips(tmp_path):
    (tmp_path / "record.zip").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    (tmp_path / "archive.zip.tmp").write_text("", encoding="utf-8")
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    (nested_dir / "nested.zip").write_text("", encoding="utf-8")

    reader = RDFDumpReader(tmp_path)

    assert [path.name for path in reader._zip_paths] == ["record.zip"]


def test_record_ordering_across_multiple_zips(tmp_path):
    _write_zip(tmp_path / "beta.zip", ["b.rdf", "a.xml"])
    _write_zip(tmp_path / "alpha.zip", ["z.rdf", "a.rdf"])

    records = list(RDFDumpReader(tmp_path))

    assert [
        (record.subdataset, record.zip_filename, record.record_path)
        for record in records
    ] == [
        ("alpha", "alpha.zip", "a.rdf"),
        ("alpha", "alpha.zip", "z.rdf"),
        ("beta", "beta.zip", "a.xml"),
        ("beta", "beta.zip", "b.rdf"),
    ]
    assert all(isinstance(record.graph, rdflib.Graph) for record in records)


def test_record_filtering_inside_zip(tmp_path):
    _write_zip(
        tmp_path / "records.zip",
        [
            "folder/",
            "folder/nested.XML",
            "ignored.txt",
            "metadata.rdf.tmp",
            "record.RDF",
            "record.xml",
        ],
    )

    records = list(RDFDumpReader(tmp_path))

    assert [record.record_path for record in records] == [
        "folder/nested.XML",
        "record.RDF",
        "record.xml",
    ]


def test_skip_subdataset_skips_remaining_records_in_current_zip(tmp_path):
    _write_zip(tmp_path / "alpha.zip", ["a.rdf", "b.rdf"])
    _write_zip(tmp_path / "beta.zip", ["c.rdf"])
    reader = RDFDumpReader(tmp_path)

    first = next(reader)
    reader.skip_subdataset()
    second = next(reader)

    assert (first.zip_filename, first.record_path) == ("alpha.zip", "a.rdf")
    assert (second.zip_filename, second.record_path) == ("beta.zip", "c.rdf")


def test_stop_iteration_after_records_are_exhausted(tmp_path):
    _write_zip(tmp_path / "records.zip", ["record.rdf"])
    reader = RDFDumpReader(tmp_path)

    assert next(reader).record_path == "record.rdf"
    with pytest.raises(StopIteration):
        next(reader)
    with pytest.raises(StopIteration):
        next(reader)


def test_valid_rdf_parsing_returns_graph(tmp_path):
    _write_zip(tmp_path / "records.zip", ["record.rdf"])

    record = next(RDFDumpReader(tmp_path))

    assert isinstance(record.graph, rdflib.Graph)
    assert len(record.graph) == 1
    assert (
        rdflib.URIRef("http://example.org/record.rdf"),
        rdflib.URIRef("http://purl.org/dc/elements/1.1/title"),
        rdflib.Literal("record.rdf"),
    ) in record.graph


def test_invalid_rdf_xml_is_skipped_by_default(tmp_path):
    _write_zip(
        tmp_path / "records.zip",
        {
            "a.rdf": INVALID_RDF,
            "b.rdf": _valid_rdf("b.rdf"),
        },
    )

    records = list(RDFDumpReader(tmp_path))

    assert [record.record_path for record in records] == ["b.rdf"]


def test_parse_error_raises_when_configured(tmp_path):
    _write_zip(tmp_path / "records.zip", {"record.rdf": INVALID_RDF})

    reader = RDFDumpReader(tmp_path, on_parse_error="raise")

    with pytest.raises(Exception):
        next(reader)


def test_invalid_uri_policy_keep_preserves_uri(tmp_path):
    _write_zip(tmp_path / "records.zip", {"record.rdf": INVALID_URI_RDF})

    record = next(RDFDumpReader(tmp_path, invalid_uri_policy="keep"))

    assert (
        rdflib.URIRef("http://example.org/invalid uri"),
        None,
        None,
    ) in record.graph


def test_invalid_uri_policy_raise_raises(tmp_path):
    _write_zip(tmp_path / "records.zip", {"record.rdf": INVALID_URI_RDF})

    reader = RDFDumpReader(tmp_path, invalid_uri_policy="raise")

    with pytest.raises(InvalidURIError):
        next(reader)
