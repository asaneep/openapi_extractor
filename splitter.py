"""OpenAPI specification splitter module."""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import logging

from core import SpecLoader, ComponentExtractor, OperationCounter, logger


class OpenAPISplitter:
    """Split large OpenAPI specs into manageable chunks while preserving references."""
    
    def __init__(self, spec_path: str, output_dir: str = "split_specs"):
        """
        Initialize the OpenAPI splitter.
        
        Args:
            spec_path: Path to the OpenAPI specification file
            output_dir: Directory to output split files
        """
        self.spec_path = Path(spec_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load the spec with error handling
        try:
            self.spec = SpecLoader.load_spec(spec_path)
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to load spec: {e}")
            raise
        
        # Extract common components
        self.common_components = ComponentExtractor.extract_components(self.spec)
    
    def analyze_spec(self) -> Dict[str, Any]:
        """
        Analyze the spec structure and size.
        
        Returns:
            Dictionary with analysis results
        """
        operation_counts = OperationCounter.count_operations(self.spec)
        
        analysis = {
            'total_endpoints': len(self.spec.get('paths', {})),
            'total_operations': operation_counts['total'],
            'operations_by_method': {
                method: count 
                for method, count in operation_counts.items() 
                if method != 'total' and count > 0
            },
            'total_schemas': len(self.spec.get('components', {}).get('schemas', {})),
            'total_responses': len(self.spec.get('components', {}).get('responses', {})),
            'total_parameters': len(self.spec.get('components', {}).get('parameters', {})),
            'has_security': 'security' in self.spec or 'securitySchemes' in self.spec.get('components', {}),
            'has_servers': 'servers' in self.spec,
            'openapi_version': self.spec.get('openapi', self.spec.get('swagger', 'unknown'))
        }
        
        return analysis
    
    def group_endpoints_by_tag(self) -> Dict[str, List[Tuple[str, str, Dict]]]:
        """
        Group endpoints by their tags for logical splitting.
        
        Returns:
            Dictionary mapping tags to list of (path, method, operation) tuples
        """
        grouped = defaultdict(list)
        untagged = []
        
        for path, path_item in self.spec.get('paths', {}).items():
            if not isinstance(path_item, dict):
                logger.warning(f"Invalid path item at {path}, skipping")
                continue
            
            # Track if any operation in this path has been tagged
            path_has_tags = False
            
            for method in OperationCounter.HTTP_METHODS:
                if method not in path_item:
                    continue
                    
                operation = path_item[method]
                if not isinstance(operation, dict):
                    logger.warning(f"Invalid operation at {method.upper()} {path}, skipping")
                    continue
                
                tags = operation.get('tags', [])
                if tags:
                    for tag in tags:
                        grouped[tag].append((path, method, operation))
                        path_has_tags = True
                else:
                    # Collect untagged operations
                    untagged.append((path, method, operation))
        
        if untagged:
            grouped['untagged'] = untagged
        
        return dict(grouped)
    
    def group_endpoints_by_path_prefix(self, max_per_file: int = 50) -> Dict[str, List[Tuple[str, str, Dict]]]:
        """
        Group endpoints by path prefix (e.g., /users, /products).
        
        Args:
            max_per_file: Maximum operations per file
            
        Returns:
            Dictionary mapping prefixes to list of (path, method, operation) tuples
        """
        grouped = defaultdict(list)
        
        for path, path_item in self.spec.get('paths', {}).items():
            if not isinstance(path_item, dict):
                continue
            
            # Extract the first significant part of the path
            parts = path.strip('/').split('/')
            prefix = parts[0] if parts and parts[0] else 'root'
            
            # Sanitize prefix for filename
            prefix = prefix.replace('{', '').replace('}', '')
            
            for method in OperationCounter.HTTP_METHODS:
                if method in path_item:
                    operation = path_item[method]
                    if isinstance(operation, dict):
                        grouped[prefix].append((path, method, operation))
        
        # Split large groups into smaller chunks
        final_groups = {}
        for prefix, endpoints in grouped.items():
            if len(endpoints) > max_per_file:
                for i in range(0, len(endpoints), max_per_file):
                    chunk_name = f"{prefix}_part{(i // max_per_file) + 1}"
                    final_groups[chunk_name] = endpoints[i:i + max_per_file]
            else:
                final_groups[prefix] = endpoints
        
        return final_groups
    
    def create_mini_spec(self, endpoints: List[Tuple[str, str, Dict]], 
                        name: str, include_components: bool = True) -> Dict[str, Any]:
        """
        Create a mini OpenAPI spec with selected endpoints.
        
        Args:
            endpoints: List of (path, method, operation) tuples
            name: Name for this split
            include_components: Whether to include shared components
            
        Returns:
            Dictionary containing the mini specification
        """
        mini_spec = {
            'openapi': self.spec.get('openapi', '3.1.0'),
            'info': self.spec.get('info', {}).copy() if 'info' in self.spec else {'title': 'API', 'version': '1.0.0'},
            'paths': {}
        }
        
        # Include components if requested
        if include_components and self.common_components:
            mini_spec['components'] = {}
            for comp_type, components in self.common_components.items():
                if components:
                    mini_spec['components'][comp_type] = components
        
        # Add servers if present
        if 'servers' in self.spec:
            mini_spec['servers'] = self.spec['servers'].copy()
        
        # Add security if present
        if 'security' in self.spec:
            mini_spec['security'] = self.spec['security'].copy()
        
        # Add relevant tags
        if 'tags' in self.spec:
            # Filter tags to only include those used in the endpoints
            used_tags = set()
            for _, _, operation in endpoints:
                if 'tags' in operation:
                    used_tags.update(operation['tags'])
            
            if used_tags:
                mini_spec['tags'] = [
                    tag for tag in self.spec['tags'] 
                    if tag.get('name') in used_tags
                ]
        
        # Add the endpoints
        for path, method, operation in endpoints:
            if path not in mini_spec['paths']:
                mini_spec['paths'][path] = {}
            mini_spec['paths'][path][method] = operation
        
        # Update info to indicate this is a split
        mini_spec['info']['title'] = f"{mini_spec['info'].get('title', 'API')} - {name}"
        mini_spec['info']['x-split-part'] = name
        mini_spec['info']['x-split-timestamp'] = Path(self.spec_path).stat().st_mtime
        
        return mini_spec
    
    def split_by_tags(self) -> Dict[str, Any]:
        """
        Split the spec by tags.
        
        Returns:
            Mapping information about the split files
        """
        logger.info("Splitting by tags...")
        grouped = self.group_endpoints_by_tag()
        
        if not grouped:
            logger.warning("No endpoints found to split")
            return {'type': 'tag-based', 'files': []}
        
        mapping = {'type': 'tag-based', 'files': [], 'source': str(self.spec_path)}
        
        for tag, endpoints in grouped.items():
            # Sanitize tag for filename
            safe_tag = tag.replace('/', '_').replace(' ', '_')
            filename = f"spec_{safe_tag}.json"
            mini_spec = self.create_mini_spec(endpoints, tag)
            
            output_path = self.output_dir / filename
            SpecLoader.save_spec(mini_spec, output_path, format='json')
            
            mapping['files'].append({
                'name': filename,
                'tag': tag,
                'endpoint_count': len(endpoints),
                'path_count': len(set(path for path, _, _ in endpoints))
            })
            logger.info(f"  Created {filename} with {len(endpoints)} operations")
        
        # Save mapping
        mapping_path = self.output_dir / 'split_mapping.json'
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
        
        logger.info(f"Split into {len(grouped)} files")
        return mapping
    
    def split_by_path_prefix(self, max_per_file: int = 50) -> Dict[str, Any]:
        """
        Split the spec by path prefix.
        
        Args:
            max_per_file: Maximum operations per file
            
        Returns:
            Mapping information about the split files
        """
        logger.info(f"Splitting by path prefix (max {max_per_file} operations per file)...")
        grouped = self.group_endpoints_by_path_prefix(max_per_file)
        
        if not grouped:
            logger.warning("No endpoints found to split")
            return {'type': 'path-based', 'files': []}
        
        mapping = {'type': 'path-based', 'files': [], 'source': str(self.spec_path)}
        
        for prefix, endpoints in grouped.items():
            filename = f"spec_{prefix}.json"
            mini_spec = self.create_mini_spec(endpoints, prefix)
            
            output_path = self.output_dir / filename
            SpecLoader.save_spec(mini_spec, output_path, format='json')
            
            mapping['files'].append({
                'name': filename,
                'prefix': prefix,
                'endpoint_count': len(endpoints),
                'path_count': len(set(path for path, _, _ in endpoints))
            })
            logger.info(f"  Created {filename} with {len(endpoints)} operations")
        
        # Save mapping
        mapping_path = self.output_dir / 'split_mapping.json'
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
        
        logger.info(f"Split into {len(grouped)} files")
        return mapping
    
    def split_by_size(self, operations_per_file: int = 30) -> Dict[str, Any]:
        """
        Split the spec into files with a fixed number of operations.
        
        Args:
            operations_per_file: Target number of operations per file
            
        Returns:
            Mapping information about the split files
        """
        logger.info(f"Splitting into files with ~{operations_per_file} operations each...")
        
        all_endpoints = OperationCounter.get_operations(self.spec)
        
        if not all_endpoints:
            logger.warning("No endpoints found to split")
            return {'type': 'size-based', 'files': []}
        
        mapping = {'type': 'size-based', 'files': [], 'source': str(self.spec_path)}
        
        for i in range(0, len(all_endpoints), operations_per_file):
            chunk = all_endpoints[i:i + operations_per_file]
            part_num = (i // operations_per_file) + 1
            filename = f"spec_part{part_num:03d}.json"
            
            mini_spec = self.create_mini_spec(chunk, f"Part {part_num}")
            
            output_path = self.output_dir / filename
            SpecLoader.save_spec(mini_spec, output_path, format='json')
            
            mapping['files'].append({
                'name': filename,
                'part': part_num,
                'endpoint_count': len(chunk),
                'path_count': len(set(path for path, _, _ in chunk))
            })
            logger.info(f"  Created {filename} with {len(chunk)} operations")
        
        # Save mapping
        mapping_path = self.output_dir / 'split_mapping.json'
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
        
        total_files = (len(all_endpoints) + operations_per_file - 1) // operations_per_file
        logger.info(f"Split into {total_files} files")
        return mapping