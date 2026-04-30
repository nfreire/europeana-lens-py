from dataclasses import dataclass
import pathlib
import zipfile
import rdflib
from rdflib.term import URIRef

try:
    from rdflib.term import _is_valid_uri
except ImportError:
    def _is_valid_uri(uri: str) -> bool:
        return not any(char in uri for char in '<>" {}|\\^`')

_ON_PARSE_ERROR_VALUES = {"skip_record", "raise"}
_INVALID_URI_POLICY_VALUES = {"keep", "raise"}
_RECORD_SUFFIXES = {".rdf", ".xml"}


class InvalidURIError(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    graph: rdflib.Graph
    subdataset: str
    zip_filename: str
    record_path: str


class RDFDumpReader:
    def __init__(
        self,
        path: str | pathlib.Path,
        *,
        on_parse_error: str = "skip_record",
        invalid_uri_policy: str = "keep",
    ) -> None:
        if on_parse_error not in _ON_PARSE_ERROR_VALUES:
            raise ValueError(f"invalid on_parse_error: {on_parse_error!r}")
        if invalid_uri_policy not in _INVALID_URI_POLICY_VALUES:
            raise ValueError(f"invalid invalid_uri_policy: {invalid_uri_policy!r}")

        input_path = pathlib.Path(path)
        if not input_path.exists():
            raise FileNotFoundError(input_path)
        if not input_path.is_dir():
            raise NotADirectoryError(input_path)

        self._path = input_path
        self._on_parse_error = on_parse_error
        self._invalid_uri_policy = invalid_uri_policy
        self._zip_paths = sorted(
            (
                child
                for child in input_path.iterdir()
                if child.is_file() and child.suffix.lower() == ".zip"
            ),
            key=lambda child: child.name,
        )
        self._zip_index = 0
        self._current_zip: zipfile.ZipFile | None = None
        self._current_zip_path: pathlib.Path | None = None
        self._current_record_paths: list[str] = []
        self._record_index = 0

    def __iter__(self) -> "RDFDumpReader":
        return self

    def __next__(self) -> Record:
        while True:
            if self._current_zip is None:
                self._open_next_zip()

            if self._current_zip is None:
                raise StopIteration

            if self._record_index < len(self._current_record_paths):
                record_path = self._current_record_paths[self._record_index]
                self._record_index += 1
                zip_path = self._current_zip_path
                zip_file = self._current_zip
                if zip_path is None or zip_file is None:
                    raise RuntimeError("reader has no active ZIP path")

                try:
                    graph = self._parse_record(zip_file, record_path)
                except Exception:
                    if self._on_parse_error == "raise":
                        raise
                    continue

                if self._invalid_uri_policy == "raise":
                    self._raise_on_invalid_uris(graph)

                return Record(
                    graph=graph,
                    subdataset=zip_path.stem,
                    zip_filename=zip_path.name,
                    record_path=record_path,
                )

            self._close_current_zip()

    def skip_subdataset(self) -> None:
        self._close_current_zip()

    def _open_next_zip(self) -> None:
        while self._zip_index < len(self._zip_paths):
            zip_path = self._zip_paths[self._zip_index]
            self._zip_index += 1

            zip_file = zipfile.ZipFile(zip_path)
            record_paths = sorted(
                info.filename
                for info in zip_file.infolist()
                if not info.is_dir()
                and pathlib.PurePosixPath(info.filename).suffix.lower()
                in _RECORD_SUFFIXES
            )

            self._current_zip = zip_file
            self._current_zip_path = zip_path
            self._current_record_paths = record_paths
            self._record_index = 0
            return

        self._current_zip = None
        self._current_zip_path = None
        self._current_record_paths = []
        self._record_index = 0

    def _parse_record(
        self, zip_file: zipfile.ZipFile, record_path: str
    ) -> rdflib.Graph:
        graph = rdflib.Graph()
        with zip_file.open(record_path) as source:
            graph.parse(source, format="xml")
        return graph

    def _raise_on_invalid_uris(self, graph: rdflib.Graph) -> None:
        for triple in graph:
            for term in triple:
                if isinstance(term, URIRef) and not _is_valid_uri(str(term)):
                    raise InvalidURIError(f"invalid URI reference: {term}")

    def _close_current_zip(self) -> None:
        if self._current_zip is not None:
            self._current_zip.close()

        self._current_zip = None
        self._current_zip_path = None
        self._current_record_paths = []
        self._record_index = 0
