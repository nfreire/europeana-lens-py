# RDF Dump Processing Library

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