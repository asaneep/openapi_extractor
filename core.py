"""Core utilities and base classes for OpenAPI specification handling."""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class SpecLoader:
    """Utility class for loading OpenAPI specifications."""
    
    @staticmethod
    def load_spec(file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load an OpenAPI specification from a file.
        
        Args:
            file_path: Path to the OpenAPI spec file (JSON or YAML)
            
        Returns:
            Dictionary containing the OpenAPI specification
            
        Raises:
            FileNotFoundError: If the spec file doesn't exist
            ValueError: If the file format is not supported or invalid
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Specification file not found: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.suffix in ['.yaml', '.yml']:
                    spec = yaml.safe_load(f)
                elif file_path.suffix == '.json':
                    spec = json.load(f)
                else:
                    raise ValueError(f"Unsupported file format: {file_path.suffix}")
                
                # Validate basic structure
                if not isinstance(spec, dict):
                    raise ValueError("Invalid spec: root must be a dictionary")
                
                if 'openapi' not in spec and 'swagger' not in spec:
                    logger.warning("No OpenAPI/Swagger version found in spec")
                
                return spec
                
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise ValueError(f"Failed to parse {file_path}: {e}")
    
    @staticmethod
    def save_spec(spec: Dict[str, Any], file_path: Union[str, Path], 
                  format: str = 'json', indent: int = 2) -> None:
        """
        Save an OpenAPI specification to a file.
        
        Args:
            spec: OpenAPI specification dictionary
            file_path: Path where to save the spec
            format: Output format ('json' or 'yaml')
            indent: Indentation level for JSON output
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if format == 'json':
                    json.dump(spec, f, indent=indent, ensure_ascii=False)
                elif format in ['yaml', 'yml']:
                    yaml.dump(spec, f, default_flow_style=False, 
                             allow_unicode=True, sort_keys=False)
                else:
                    raise ValueError(f"Unsupported format: {format}")
            
            logger.info(f"Saved spec to {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to save spec to {file_path}: {e}")
            raise


class ComponentExtractor:
    """Extract and manage OpenAPI components."""
    
    COMPONENT_TYPES = [
        'schemas', 'responses', 'parameters', 'examples',
        'requestBodies', 'headers', 'securitySchemes', 
        'links', 'callbacks'
    ]
    
    @classmethod
    def extract_components(cls, spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Extract all components from an OpenAPI specification.
        
        Args:
            spec: OpenAPI specification dictionary
            
        Returns:
            Dictionary of component types and their definitions
        """
        components = {comp_type: {} for comp_type in cls.COMPONENT_TYPES}
        
        if 'components' in spec:
            for comp_type in cls.COMPONENT_TYPES:
                if comp_type in spec['components']:
                    components[comp_type] = spec['components'][comp_type].copy()
        
        return components
    
    @classmethod
    def merge_components(cls, target: Dict[str, Any], source: Dict[str, Any],
                        conflict_strategy: str = 'keep_first') -> Dict[str, int]:
        """
        Merge components from source into target.
        
        Args:
            target: Target component dictionary to merge into
            source: Source component dictionary to merge from
            conflict_strategy: How to handle conflicts ('keep_first', 'keep_last', 'error')
            
        Returns:
            Dictionary with conflict counts per component type
        """
        conflicts = {comp_type: 0 for comp_type in cls.COMPONENT_TYPES}
        
        for comp_type in cls.COMPONENT_TYPES:
            if comp_type not in source:
                continue
                
            if comp_type not in target:
                target[comp_type] = {}
            
            for name, definition in source[comp_type].items():
                if name in target[comp_type]:
                    # Check if definitions are different
                    existing = json.dumps(target[comp_type][name], sort_keys=True)
                    new = json.dumps(definition, sort_keys=True)
                    
                    if existing != new:
                        conflicts[comp_type] += 1
                        
                        if conflict_strategy == 'error':
                            raise ValueError(f"Conflicting {comp_type} '{name}'")
                        elif conflict_strategy == 'keep_last':
                            target[comp_type][name] = definition
                            logger.warning(f"Overwriting {comp_type} '{name}'")
                        else:  # keep_first
                            logger.debug(f"Keeping existing {comp_type} '{name}'")
                else:
                    target[comp_type][name] = definition
        
        return conflicts


class OperationCounter:
    """Count operations in OpenAPI specifications."""
    
    HTTP_METHODS = ['get', 'post', 'put', 'delete', 'patch', 'options', 'head', 'trace']
    
    @classmethod
    def count_operations(cls, spec: Dict[str, Any]) -> Dict[str, int]:
        """
        Count operations in an OpenAPI specification.
        
        Args:
            spec: OpenAPI specification dictionary
            
        Returns:
            Dictionary with operation counts by method
        """
        counts = {method: 0 for method in cls.HTTP_METHODS}
        counts['total'] = 0
        
        paths = spec.get('paths', {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
                
            for method in cls.HTTP_METHODS:
                if method in path_item:
                    counts[method] += 1
                    counts['total'] += 1
        
        return counts
    
    @classmethod
    def get_operations(cls, spec: Dict[str, Any]) -> list:
        """
        Get all operations from an OpenAPI specification.
        
        Args:
            spec: OpenAPI specification dictionary
            
        Returns:
            List of tuples (path, method, operation)
        """
        operations = []
        paths = spec.get('paths', {})
        
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
                
            for method in cls.HTTP_METHODS:
                if method in path_item:
                    operations.append((path, method, path_item[method]))
        
        return operations


def validate_spec_structure(spec: Dict[str, Any]) -> list:
    """
    Validate the basic structure of an OpenAPI specification.
    
    Args:
        spec: OpenAPI specification dictionary
        
    Returns:
        List of validation warnings/errors
    """
    issues = []
    
    # Check for OpenAPI version
    if 'openapi' not in spec and 'swagger' not in spec:
        issues.append("Missing OpenAPI/Swagger version field")
    
    # Check for info object
    if 'info' not in spec:
        issues.append("Missing 'info' object")
    elif not isinstance(spec['info'], dict):
        issues.append("'info' must be an object")
    else:
        if 'title' not in spec['info']:
            issues.append("Missing 'info.title'")
        if 'version' not in spec['info']:
            issues.append("Missing 'info.version'")
    
    # Check paths
    if 'paths' not in spec:
        issues.append("Missing 'paths' object")
    elif not isinstance(spec['paths'], dict):
        issues.append("'paths' must be an object")
    elif not spec['paths']:
        issues.append("'paths' is empty")
    
    # Check components structure if present
    if 'components' in spec:
        if not isinstance(spec['components'], dict):
            issues.append("'components' must be an object")
    
    return issues