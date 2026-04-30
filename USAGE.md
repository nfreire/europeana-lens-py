# rdf-dump-reader – Usage

## Purpose

Iterate over record-based RDF dumps stored as ZIP archives containing RDF/XML files.

## Basic usage

```python
from rdf_dump_reader import RDFDumpReader

reader = RDFDumpReader(
    "/path/to/dump",
    on_parse_error="skip_record",
    invalid_uri_policy="keep",
)

for record in reader:
    graph = record.graph
    subdataset = record.subdataset
    zip_filename = record.zip_filename
    record_path = record.record_path
```	
	
## Behavior guarantees
- One rdflib.Graph per record
- Streaming processing (no full dataset in memory)
- Deterministic ordering (ZIPs and records lexicographically)
- RDF/XML parse errors: skipped by default (skip_record)
- Invalid URIs: preserved if RDFLib parsing succeeds
	
	
## Control flow

- Stop processing: break the loop
- Skip remaining records in the current subdataset:

```python
reader.skip_subdataset()
```

## Constraints

- Only RDF/XML is supported
- Input must be a local filesystem directory
- Each record is independent; do not assume a global RDF graph