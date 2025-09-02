"""OpenAPI specification merger module."""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from core import SpecLoader, ComponentExtractor, logger


class OpenAPIMerger:
    """Merge split OpenAPI specs back into a single file."""
    
    def __init__(self, input_dir: str = "split_specs", output_path: str = "merged_spec.json"):
        """
        Initialize the OpenAPI merger.
        
        Args:
            input_dir: Directory containing split spec files
            output_path: Path for the merged output file
        """
        self.input_dir = Path(input_dir)
        self.output_path = Path(output_path)
        
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {self.input_dir}")
        
        # Initialize merged spec structure
        self.merged_spec = {
            'openapi': '3.1.0',
            'info': {
                'title': 'Merged API',
                'version': '1.0.0'
            },
            'paths': {},
            'components': {}
        }
        
        # Track merge statistics
        self.stats = {
            'files_processed': 0,
            'paths_merged': 0,
            'operations_merged': 0,
            'component_conflicts': {},
            'path_conflicts': 0
        }
    
    def load_mapping(self) -> Optional[Dict[str, Any]]:
        """
        Load the split mapping file if it exists.
        
        Returns:
            Mapping dictionary or None if not found
        """
        mapping_path = self.input_dir / 'split_mapping.json'
        if mapping_path.exists():
            try:
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load mapping file: {e}")
        return None
    
    def get_spec_files(self) -> List[Path]:
        """
        Get list of spec files to merge.
        
        Returns:
            List of spec file paths
        """
        mapping = self.load_mapping()
        
        if mapping and 'files' in mapping:
            # Use files from mapping
            files = []
            for file_info in mapping['files']:
                file_path = self.input_dir / file_info['name']
                if file_path.exists():
                    files.append(file_path)
                else:
                    logger.warning(f"File from mapping not found: {file_path}")
            return files
        else:
            # Find all spec files in directory
            files = list(self.input_dir.glob("spec_*.json"))
            files.extend(self.input_dir.glob("spec_*.yaml"))
            files.extend(self.input_dir.glob("spec_*.yml"))
            return sorted(files)
    
    def merge_info(self, spec: Dict[str, Any]) -> None:
        """
        Merge info section from a spec.
        
        Args:
            spec: Spec to merge info from
        """
        if 'info' not in spec:
            return
        
        source_info = spec['info']
        
        # On first spec, copy most of the info
        if self.stats['files_processed'] == 0:
            self.merged_spec['info'] = source_info.copy()
            
            # Remove split indicators
            for key in ['x-split-part', 'x-split-timestamp']:
                if key in self.merged_spec['info']:
                    del self.merged_spec['info'][key]
            
            # Clean up title if it contains split suffix
            title = self.merged_spec['info'].get('title', '')
            if ' - ' in title:
                # Remove the split part suffix
                self.merged_spec['info']['title'] = title.split(' - ')[0]
        else:
            # For subsequent specs, only merge non-conflicting metadata
            if 'description' in source_info and 'description' not in self.merged_spec['info']:
                self.merged_spec['info']['description'] = source_info['description']
            
            # Merge extensions (x- fields) that don't conflict
            for key, value in source_info.items():
                if key.startswith('x-') and key not in ['x-split-part', 'x-split-timestamp']:
                    if key not in self.merged_spec['info']:
                        self.merged_spec['info'][key] = value
    
    def merge_root_properties(self, spec: Dict[str, Any]) -> None:
        """
        Merge root-level properties from a spec.
        
        Args:
            spec: Spec to merge properties from
        """
        # Properties that should be merged (not paths or components)
        mergeable_props = ['servers', 'security', 'tags', 'externalDocs']
        
        for prop in mergeable_props:
            if prop not in spec:
                continue
            
            if prop not in self.merged_spec:
                self.merged_spec[prop] = spec[prop].copy()
            elif prop == 'servers':
                # Merge servers, avoiding duplicates
                existing_servers = {json.dumps(s, sort_keys=True) for s in self.merged_spec[prop]}
                for server in spec[prop]:
                    server_json = json.dumps(server, sort_keys=True)
                    if server_json not in existing_servers:
                        self.merged_spec[prop].append(server)
                        existing_servers.add(server_json)
            elif prop == 'tags':
                # Merge tags, avoiding duplicates by name
                existing_tags = {tag['name']: tag for tag in self.merged_spec[prop]}
                for tag in spec[prop]:
                    if tag['name'] not in existing_tags:
                        self.merged_spec[prop].append(tag)
                    else:
                        # Update description if more detailed
                        if 'description' in tag and 'description' not in existing_tags[tag['name']]:
                            existing_tags[tag['name']]['description'] = tag['description']
    
    def merge_paths(self, spec: Dict[str, Any]) -> None:
        """
        Merge paths from a spec into the merged spec.
        
        Args:
            spec: Spec to merge paths from
        """
        if 'paths' not in spec:
            return
        
        for path, path_item in spec['paths'].items():
            if not isinstance(path_item, dict):
                logger.warning(f"Invalid path item at {path}, skipping")
                continue
            
            if path not in self.merged_spec['paths']:
                self.merged_spec['paths'][path] = {}
                self.stats['paths_merged'] += 1
            
            for method, operation in path_item.items():
                if method in self.merged_spec['paths'][path]:
                    self.stats['path_conflicts'] += 1
                    logger.warning(f"Duplicate operation: {method.upper()} {path}")
                
                self.merged_spec['paths'][path][method] = operation
                if method in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head', 'trace']:
                    self.stats['operations_merged'] += 1
    
    def merge_components(self, spec: Dict[str, Any], conflict_strategy: str = 'keep_first') -> None:
        """
        Merge components from a spec into the merged spec.
        
        Args:
            spec: Spec to merge components from
            conflict_strategy: How to handle conflicts ('keep_first', 'keep_last', 'error')
        """
        if 'components' not in spec:
            return
        
        if 'components' not in self.merged_spec:
            self.merged_spec['components'] = {}
        
        # Use ComponentExtractor for proper merging
        source_components = spec['components']
        target_components = self.merged_spec['components']
        
        conflicts = ComponentExtractor.merge_components(
            target_components, 
            source_components, 
            conflict_strategy
        )
        
        # Track conflicts in stats
        for comp_type, count in conflicts.items():
            if count > 0:
                if comp_type not in self.stats['component_conflicts']:
                    self.stats['component_conflicts'][comp_type] = 0
                self.stats['component_conflicts'][comp_type] += count
    
    def clean_merged_spec(self) -> None:
        """Clean up the merged specification."""
        # Remove empty component sections
        if 'components' in self.merged_spec:
            empty_components = []
            for comp_type, components in self.merged_spec['components'].items():
                if not components:
                    empty_components.append(comp_type)
            
            for comp_type in empty_components:
                del self.merged_spec['components'][comp_type]
            
            # Remove components entirely if empty
            if not self.merged_spec['components']:
                del self.merged_spec['components']
        
        # Ensure paths is not empty
        if not self.merged_spec.get('paths'):
            logger.warning("Merged spec has no paths!")
    
    def merge_all(self, conflict_strategy: str = 'keep_first', 
                  output_format: str = 'json') -> Dict[str, Any]:
        """
        Merge all split files back into one.
        
        Args:
            conflict_strategy: How to handle conflicts
            output_format: Output format ('json' or 'yaml')
            
        Returns:
            Statistics about the merge operation
        """
        logger.info("Starting merge operation...")
        
        spec_files = self.get_spec_files()
        
        if not spec_files:
            raise ValueError("No spec files found to merge!")
        
        logger.info(f"Found {len(spec_files)} files to merge")
        
        # Process each file
        for file_path in spec_files:
            logger.info(f"Processing {file_path.name}...")
            
            try:
                spec = SpecLoader.load_spec(file_path)
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {e}")
                continue
            
            # Merge different sections
            if self.stats['files_processed'] == 0:
                # First file - copy OpenAPI version
                if 'openapi' in spec:
                    self.merged_spec['openapi'] = spec['openapi']
                elif 'swagger' in spec:
                    self.merged_spec['swagger'] = spec['swagger']
            
            self.merge_info(spec)
            self.merge_root_properties(spec)
            self.merge_components(spec, conflict_strategy)
            self.merge_paths(spec)
            
            self.stats['files_processed'] += 1
        
        # Clean up the merged spec
        self.clean_merged_spec()
        
        # Save the merged spec
        logger.info(f"Saving merged spec to {self.output_path}")
        SpecLoader.save_spec(self.merged_spec, self.output_path, format=output_format)
        
        # Log statistics
        logger.info("Merge completed successfully!")
        logger.info(f"  Files processed: {self.stats['files_processed']}")
        logger.info(f"  Paths merged: {self.stats['paths_merged']}")
        logger.info(f"  Operations merged: {self.stats['operations_merged']}")
        
        if self.stats['path_conflicts'] > 0:
            logger.warning(f"  Path conflicts: {self.stats['path_conflicts']}")
        
        if self.stats['component_conflicts']:
            logger.warning("  Component conflicts:")
            for comp_type, count in self.stats['component_conflicts'].items():
                logger.warning(f"    {comp_type}: {count}")
        
        return self.stats
    
    def validate_merged_spec(self) -> List[str]:
        """
        Validate the merged specification.
        
        Returns:
            List of validation issues
        """
        from core import validate_spec_structure
        return validate_spec_structure(self.merged_spec)