# OpenAPI Specification Tools

A comprehensive toolkit for managing large OpenAPI specifications by splitting, merging, and analyzing them.

## Features

- **Split** large OpenAPI specs into smaller, manageable files
- **Merge** split specs back into a single file
- **Analyze** spec structure, complexity, and quality
- **Validate** spec structure and identify issues
- Support for both JSON and YAML formats
- Intelligent handling of components and references
- Multiple splitting strategies (by tags, paths, or size)

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd openapi_ext_1

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Command Line Interface

The main entry point is the `cli.py` script which provides several commands:

```bash
# Make the CLI executable
chmod +x cli.py

# Show help
python cli.py --help
```

### Splitting Specifications

Split a large OpenAPI spec into smaller files using different strategies:

#### Split by Tags
Groups endpoints by their tags for logical separation:

```bash
python cli.py split api.json --method tags
```

#### Split by Path Prefix
Groups endpoints by their path prefix (e.g., /users, /products):

```bash
python cli.py split api.yaml --method path --max-operations 50
```

#### Split by Size
Creates files with a fixed number of operations:

```bash
python cli.py split api.json --method size --max-operations 30
```

### Merging Specifications

Merge split specifications back into a single file:

```bash
# Basic merge
python cli.py merge --input-dir split_specs --output merged.json

# Merge with validation
python cli.py merge --validate

# Handle conflicts differently
python cli.py merge --conflict-strategy keep_last
```

### Analyzing Specifications

Get detailed analysis of your OpenAPI specification:

```bash
# Basic analysis
python cli.py analyze api.json

# Full detailed analysis
python cli.py analyze api.json --full

# Analyze specific section
python cli.py analyze api.json --section paths

# Save analysis to file
python cli.py analyze api.json --full --output analysis.json
```

### Validating Specifications

Check if your specification is valid:

```bash
python cli.py validate api.yaml
```

## Module Structure

The tool is organized into several focused modules:

### `core.py`
Core utilities and base classes:
- `SpecLoader`: Load and save OpenAPI specifications
- `ComponentExtractor`: Extract and manage components
- `OperationCounter`: Count and analyze operations
- `validate_spec_structure`: Basic structure validation

### `splitter.py`
OpenAPI specification splitter:
- `OpenAPISplitter`: Main class for splitting specs
- Multiple splitting strategies
- Preserves references and components

### `merger.py`
OpenAPI specification merger:
- `OpenAPIMerger`: Main class for merging specs
- Conflict resolution strategies
- Component deduplication

### `analyzer.py`
OpenAPI specification analyzer:
- `OpenAPIAnalyzer`: Comprehensive spec analysis
- Complexity scoring
- Quality recommendations
- Security analysis

### `cli.py`
Command-line interface:
- Argument parsing
- Command routing
- Output formatting

## Examples

### Example 1: Split and Merge Workflow

```bash
# 1. Analyze the original spec
python cli.py analyze large_api.json

# 2. Split by tags
python cli.py split large_api.json --method tags --output-dir api_parts

# 3. Work on individual parts
# ... edit files in api_parts/ ...

# 4. Merge back together
python cli.py merge --input-dir api_parts --output updated_api.json

# 5. Validate the result
python cli.py validate updated_api.json
```

### Example 2: Analyzing API Complexity

```bash
# Get full analysis with recommendations
python cli.py analyze api.yaml --full --json-output > analysis.json

# Check specific aspects
python cli.py analyze api.yaml --section security
python cli.py analyze api.yaml --section complexity
```

## Output Files

### Split Mapping
When splitting, a `split_mapping.json` file is created containing:
- Split method used
- List of generated files
- Operation counts per file
- Source file information

### Merged Specifications
Merged files include:
- All paths from split files
- Deduplicated components
- Merged metadata
- Preserved references

## Error Handling

The tool includes comprehensive error handling for:
- Missing or invalid files
- Malformed JSON/YAML
- Empty specifications
- Invalid references
- Component conflicts

## Best Practices

1. **Before Splitting**: Analyze your spec to understand its structure
2. **Choose the Right Method**: 
   - Use `tags` for logically organized APIs
   - Use `path` for RESTful APIs with clear resource boundaries
   - Use `size` for evenly distributed splits
3. **Version Control**: Keep split files in version control
4. **Validation**: Always validate after merging
5. **Component Management**: Review unused components regularly

## Limitations

- Preserves most OpenAPI 3.x features
- Some vendor extensions may need manual review
- Complex circular references require careful handling

## Contributing

Contributions are welcome! Please ensure:
- Code follows Python best practices
- Error handling is comprehensive
- Logging is informative
- Documentation is updated

## License

[Your License Here]