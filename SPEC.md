# RDF Dump Processing Library - Specification

## 1. Purpose

Provide a Python library to iterate over record-based RDF datasets stored as ZIP archives containing RDF/XML files, exposing each record as an `rdflib.Graph` together with source metadata.

The library is intended for large, heterogeneous RDF dumps where processing must be streaming, record-oriented, and tolerant of record-level parse failures.

## 2. Scope

### 2.1 In scope

- Reading ZIP archives from a local filesystem directory
- Treating each ZIP archive as one sub-dataset
- Iterating over RDF/XML files inside each ZIP archive
- Parsing each RDF/XML file into an `rdflib.Graph`
- Yielding one record at a time to user code
- Supporting user-controlled iteration using Python's iterator protocol
- Supporting skipping of the remaining records in the current sub-dataset
- Preserving invalid URI references when RDFLib can parse them
- Skipping records that cannot be parsed as RDF/XML, by default

### 2.2 Out of scope

- RDF transformation, validation, enrichment, or normalization
- RDF serialization output
- Persistence or storage of processed data
- Dataset-level graph merging
- Support for RDF serializations other than RDF/XML
- Network-based access to dumps
- Parallel processing
- Progress bars, UI components, or command-line tooling

## 3. Dataset Model

- A dump is a local directory containing ZIP archives
- Each ZIP archive represents one sub-dataset
- The sub-dataset identifier is the ZIP filename without the `.zip` extension
- Each ZIP archive contains zero or more RDF/XML record files
- Each RDF/XML file represents one logical record
- Records are independent; the library MUST NOT assume that all records together form one RDF graph

## 4. Functional Requirements

### 4.1 Input

The main input is a local filesystem directory path.

The path MUST identify an existing directory. If the path does not exist, or is not a directory, initialization MUST raise an exception.

### 4.2 ZIP discovery

The library MUST discover ZIP archives directly contained in the input directory.

Rules:

- Files with extension `.zip` MUST be included
- Extension matching SHOULD be case-insensitive
- Nested directories MUST NOT be traversed
- Non-ZIP files MUST be ignored

### 4.3 Record file discovery inside ZIP archives

Within each ZIP archive, the library MUST identify eligible RDF/XML files.

Rules:

- Files with extensions `.rdf` and `.xml` MUST be treated as candidate RDF/XML record files
- Extension matching SHOULD be case-insensitive
- Directory entries inside ZIP archives MUST be ignored
- Other files inside ZIP archives MUST be ignored
- The library MUST NOT inspect file content merely to decide whether a file is RDF/XML; parsing is the authoritative test

### 4.4 Processing

The library MUST:

- Process ZIP archives sequentially
- Process record files inside each ZIP archive sequentially
- Open and parse one record file at a time
- Yield one parsed `Record` object at a time
- Avoid loading the full dump, a full ZIP archive, or all records into memory

### 4.5 Output

For each successfully parsed record, the library MUST yield a `Record` object containing:

- The parsed RDF graph
- The sub-dataset identifier
- The record path inside the ZIP archive
- The source ZIP filename

## 5. Public API

The library MUST use a Python iterator-based pull model.

The user controls processing by repeatedly requesting the next record from the reader. The library MUST NOT use callbacks or visitor-style processing as the primary API.

### 5.1 Main reader

```python
class RDFDumpReader:
    def __init__(
        self,
        path: str | pathlib.Path,
        *,
        on_parse_error: str = "skip_record",
        invalid_uri_policy: str = "keep",
    ) -> None: ...

    def __iter__(self) -> "RDFDumpReader": ...

    def __next__(self) -> "Record": ...

    def skip_subdataset(self) -> None: ...
```

### 5.2 Record object

```python
from dataclasses import dataclass
from pathlib import Path
import rdflib

@dataclass(frozen=True)
class Record:
    graph: rdflib.Graph
    subdataset: str
    zip_filename: str
    record_path: str
```

Field semantics:

- `graph`: parsed RDF/XML record as an `rdflib.Graph`
- `subdataset`: ZIP filename without the final `.zip` extension
- `zip_filename`: basename of the source ZIP archive, including `.zip`
- `record_path`: path/name of the RDF/XML file inside the ZIP archive

### 5.3 Iteration semantics

- `RDFDumpReader` MUST be its own iterator
- `__iter__()` MUST return `self`
- `__next__()` MUST return the next successfully parsed `Record`
- Records that fail RDF/XML parsing MUST be skipped by default
- When no further records are available, `__next__()` MUST raise `StopIteration`
- Users may stop processing at any time by stopping iteration, e.g. with `break`
- No explicit `stop()` method is required

### 5.4 Skipping a sub-dataset

`skip_subdataset()` skips all remaining records in the currently active ZIP archive.

Semantics:

- If called after a record has been yielded, the next call to `__next__()` MUST continue with the first eligible record in the next ZIP archive
- If the current ZIP archive has no remaining eligible records, the next call to `__next__()` MUST continue normally with the next ZIP archive
- If called before iteration starts, it SHOULD have no effect
- If called after iteration is exhausted, it SHOULD have no effect
- It MUST NOT delete, modify, or otherwise alter the ZIP archive or its contents

### 5.5 Example usage

```python
from rdf_dump_reader import RDFDumpReader

reader = RDFDumpReader("/path/to/dump")

for record in reader:
    process(record.graph)

    if should_skip_current_subdataset(record):
        reader.skip_subdataset()

    if should_stop_processing(record):
        break
```

## 6. RDF Library and Data Model

### 6.1 RDF library

The library MUST use RDFLib.

Requirement:

```text
rdflib >= 7.0
```

Each RDF/XML record MUST be parsed using RDFLib equivalent to:

```python
graph = rdflib.Graph()
graph.parse(source, format="xml")
```

### 6.2 RDF graph representation

- Each successfully parsed record MUST be returned as a separate `rdflib.Graph`
- The library MUST NOT merge records into a shared graph
- The library MUST NOT mutate RDF terms after parsing unless explicitly required by this specification

### 6.3 Invalid URI handling

Input RDF/XML files may contain URI references that are not valid URI references according to RDFLib or URI syntax rules.

The default behavior MUST be:

```python
invalid_uri_policy="keep"
```

Supported values:

- `"keep"`: keep invalid URI references as parsed by RDFLib (default)
- `"raise"`: raise an exception when an invalid URI reference is detected in an otherwise parsed graph

Requirements for `"keep"`:

- Records containing invalid URI references MUST still be processed whenever RDFLib parsing succeeds
- Triples containing invalid URI references MUST be preserved in the returned `rdflib.Graph`
- Invalid URI references MUST NOT be silently normalized, percent-encoded, rewritten, dropped, or replaced with blank nodes
- The original lexical form of each URI reference MUST be preserved as represented by RDFLib
- The returned graph MAY contain URI references that RDFLib accepts but later warns are not valid

Requirements for `"raise"`:

- After parsing succeeds, the library MUST inspect RDF URI terms in the graph
- If an invalid URI reference is detected, the library MUST raise an exception
- This exception MUST be distinct from RDF/XML parse errors

### 6.4 Parser limitations

Lenient URI handling applies only when RDFLib can parse the RDF/XML document into RDF terms.

If the XML is not well-formed, or if RDFLib fails before a graph can be created, the record MUST be handled according to `on_parse_error`.

## 7. Error Handling

### 7.1 Configuration validation

The library MUST validate option values during initialization.

Allowed values:

```python
on_parse_error in {"skip_record", "raise"}
invalid_uri_policy in {"keep", "raise"}
```

Invalid option values MUST raise `ValueError`.

### 7.2 Invalid input directory

If the input path does not exist or is not a directory, initialization MUST raise an exception.

Recommended exception type: `FileNotFoundError` for missing paths and `NotADirectoryError` for paths that are not directories.

### 7.3 Invalid ZIP archives

Invalid ZIP archives MUST raise an exception and stop processing.

Recommended exception type: `zipfile.BadZipFile`.

### 7.4 RDF/XML parse errors

RDF/XML parse errors are errors that prevent a candidate record file from being parsed into an RDF graph.

The default behavior MUST be:

```python
on_parse_error="skip_record"
```

Supported values:

- `"skip_record"`: skip the current record and continue with the next eligible RDF/XML file (default)
- `"raise"`: raise an exception and stop processing

Skipped records MUST NOT be yielded.

### 7.5 Invalid URI errors

Invalid URI references that are present in an otherwise parseable RDF/XML file MUST be handled according to `invalid_uri_policy`.

Invalid URI handling MUST be separate from RDF/XML parse-error handling.

## 8. Ordering

Ordering MUST be deterministic.

- ZIP archives MUST be processed in lexicographical order by filename
- Record files inside each ZIP archive MUST be processed in lexicographical order by their path inside the ZIP archive
- Ordering MUST be based on the names as stored, not on filesystem modification time

## 9. Performance and Resource Constraints

- The library MUST support large dumps through streaming iteration
- The library MUST NOT load all ZIP archives into memory
- The library MUST NOT load all records from a ZIP archive into memory
- At most one record graph SHOULD be held by the library at a time, excluding references retained by user code
- ZIP archives SHOULD be opened only while their records are being processed
- File handles MUST be released when processing moves past a ZIP archive or when iteration is exhausted

## 10. Dependencies and Packaging

### 10.1 Runtime dependencies

- Python >= 3.10
- `rdflib >= 7.0`

### 10.2 Packaging

The project SHOULD use `pyproject.toml`.

The package name SHOULD be configurable by the implementer, but examples may use:

```text
rdf_dump_reader
```

## 11. Testing Requirements

The test suite MUST use `pytest`.

Tests MUST cover:

- Initialization with valid and invalid input paths
- Discovery of ZIP archives
- Ignoring non-ZIP files in the input directory
- Deterministic ZIP ordering
- Discovery of `.rdf` and `.xml` files inside ZIP archives
- Ignoring directory entries and non-RDF/XML files inside ZIP archives
- Deterministic record ordering inside ZIP archives
- Yielding `Record` objects with correct metadata
- Parsing valid RDF/XML into `rdflib.Graph`
- Skipping records with RDF/XML parse errors when `on_parse_error="skip_record"`
- Raising on RDF/XML parse errors when `on_parse_error="raise"`
- Preserving invalid URI references when `invalid_uri_policy="keep"`, where RDFLib parsing succeeds
- Raising on invalid URI references when `invalid_uri_policy="raise"`
- `skip_subdataset()` behavior after a yielded record
- Stopping iteration by breaking out of a `for` loop
- Exhaustion behavior and `StopIteration`
- Rejection of invalid option values

## 12. Documentation Requirements

Documentation MUST include:

- Installation instructions
- Minimal usage example
- Explanation of the dataset layout
- Explanation of iteration behavior
- Explanation of `skip_subdataset()`
- Explanation of parse-error behavior
- Explanation of invalid URI behavior and its RDFLib-dependent limitations

## 13. Acceptance Criteria

The implementation is acceptable when:

- A user can instantiate `RDFDumpReader` with a directory containing ZIP archives
- The reader yields one `Record` per successfully parsed RDF/XML record file
- Each yielded `Record` contains an `rdflib.Graph` and correct source metadata
- ZIP archives and records are processed in deterministic lexicographical order
- Records with RDF/XML parse errors are skipped by default
- Invalid URI references are preserved by default when RDFLib parsing succeeds
- The user can skip the rest of the current sub-dataset using `skip_subdataset()`
- The user can stop processing by ending iteration
- The implementation avoids loading the full dump or full ZIP contents into memory
- The test suite covers the required behavior

