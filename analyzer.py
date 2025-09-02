"""OpenAPI specification analyzer module."""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
import logging

from core import SpecLoader, OperationCounter, ComponentExtractor, validate_spec_structure, logger


class OpenAPIAnalyzer:
    """Analyze OpenAPI specifications for structure, complexity, and quality."""
    
    def __init__(self, spec_path: str):
        """
        Initialize the OpenAPI analyzer.
        
        Args:
            spec_path: Path to the OpenAPI specification file
        """
        self.spec_path = Path(spec_path)
        
        # Load the spec with error handling
        try:
            self.spec = SpecLoader.load_spec(spec_path)
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to load spec: {e}")
            raise
    
    def get_basic_info(self) -> Dict[str, Any]:
        """
        Get basic information about the specification.
        
        Returns:
            Dictionary with basic spec information
        """
        info = self.spec.get('info', {})
        
        return {
            'title': info.get('title', 'Unknown'),
            'version': info.get('version', 'Unknown'),
            'description': info.get('description', 'No description'),
            'openapi_version': self.spec.get('openapi', self.spec.get('swagger', 'Unknown')),
            'file_size': self.spec_path.stat().st_size if self.spec_path.exists() else 0,
            'file_path': str(self.spec_path)
        }
    
    def analyze_paths(self) -> Dict[str, Any]:
        """
        Analyze the paths and operations in the specification.
        
        Returns:
            Dictionary with path analysis results
        """
        paths = self.spec.get('paths', {})
        operation_counts = OperationCounter.count_operations(self.spec)
        
        # Analyze path patterns
        path_patterns = defaultdict(int)
        path_depths = []
        parameterized_paths = 0
        
        for path in paths.keys():
            # Count path parameters
            if '{' in path:
                parameterized_paths += 1
            
            # Analyze path depth
            depth = len([p for p in path.split('/') if p])
            path_depths.append(depth)
            
            # Extract base pattern
            base = path.split('/')[1] if len(path.split('/')) > 1 else 'root'
            path_patterns[base] += 1
        
        return {
            'total_paths': len(paths),
            'total_operations': operation_counts['total'],
            'operations_by_method': {
                method: count 
                for method, count in operation_counts.items() 
                if method != 'total' and count > 0
            },
            'parameterized_paths': parameterized_paths,
            'average_path_depth': sum(path_depths) / len(path_depths) if path_depths else 0,
            'max_path_depth': max(path_depths) if path_depths else 0,
            'path_patterns': dict(path_patterns),
            'paths_without_operations': len([p for p in paths.values() if not any(
                m in p for m in OperationCounter.HTTP_METHODS
            )])
        }
    
    def analyze_components(self) -> Dict[str, Any]:
        """
        Analyze the components in the specification.
        
        Returns:
            Dictionary with component analysis results
        """
        components = self.spec.get('components', {})
        
        analysis = {
            'has_components': bool(components),
            'component_counts': {},
            'reusability_score': 0
        }
        
        total_refs = 0
        unique_refs = set()
        
        # Count each component type
        for comp_type in ComponentExtractor.COMPONENT_TYPES:
            if comp_type in components:
                count = len(components[comp_type])
                analysis['component_counts'][comp_type] = count
                
                # Track references for reusability analysis
                for name in components[comp_type].keys():
                    ref = f"#/components/{comp_type}/{name}"
                    unique_refs.add(ref)
        
        # Analyze reference usage throughout the spec
        def count_refs(obj, refs_found: Set[str]):
            """Recursively count $ref usage."""
            if isinstance(obj, dict):
                if '$ref' in obj:
                    refs_found.add(obj['$ref'])
                    return 1
                return sum(count_refs(v, refs_found) for v in obj.values())
            elif isinstance(obj, list):
                return sum(count_refs(item, refs_found) for item in obj)
            return 0
        
        refs_used = set()
        total_refs = count_refs(self.spec, refs_used)
        
        # Calculate reusability score
        if unique_refs:
            refs_actually_used = refs_used.intersection(unique_refs)
            analysis['reusability_score'] = len(refs_actually_used) / len(unique_refs)
            analysis['unused_components'] = len(unique_refs - refs_actually_used)
            analysis['total_references'] = total_refs
        
        return analysis
    
    def analyze_tags(self) -> Dict[str, Any]:
        """
        Analyze tag usage in the specification.
        
        Returns:
            Dictionary with tag analysis results
        """
        defined_tags = {tag['name']: tag for tag in self.spec.get('tags', [])}
        used_tags = defaultdict(int)
        untagged_operations = 0
        
        # Count tag usage in operations
        for path, path_item in self.spec.get('paths', {}).items():
            if not isinstance(path_item, dict):
                continue
            
            for method in OperationCounter.HTTP_METHODS:
                if method in path_item:
                    operation = path_item[method]
                    if isinstance(operation, dict):
                        tags = operation.get('tags', [])
                        if tags:
                            for tag in tags:
                                used_tags[tag] += 1
                        else:
                            untagged_operations += 1
        
        # Find undefined tags (used but not defined)
        undefined_tags = set(used_tags.keys()) - set(defined_tags.keys())
        
        # Find unused tags (defined but not used)
        unused_tags = set(defined_tags.keys()) - set(used_tags.keys())
        
        return {
            'defined_tags': len(defined_tags),
            'used_tags': len(used_tags),
            'undefined_tags': list(undefined_tags),
            'unused_tags': list(unused_tags),
            'untagged_operations': untagged_operations,
            'tag_usage': dict(used_tags),
            'average_operations_per_tag': (
                sum(used_tags.values()) / len(used_tags) if used_tags else 0
            )
        }
    
    def analyze_security(self) -> Dict[str, Any]:
        """
        Analyze security definitions and usage.
        
        Returns:
            Dictionary with security analysis results
        """
        analysis = {
            'has_security': False,
            'security_schemes': [],
            'global_security': [],
            'operations_with_security': 0,
            'operations_without_security': 0
        }
        
        # Check for security schemes
        if 'components' in self.spec and 'securitySchemes' in self.spec['components']:
            schemes = self.spec['components']['securitySchemes']
            analysis['security_schemes'] = list(schemes.keys())
            analysis['has_security'] = True
        
        # Check global security
        if 'security' in self.spec:
            analysis['global_security'] = self.spec['security']
            analysis['has_security'] = True
        
        # Count operations with/without security
        for path, path_item in self.spec.get('paths', {}).items():
            if not isinstance(path_item, dict):
                continue
            
            for method in OperationCounter.HTTP_METHODS:
                if method in path_item:
                    operation = path_item[method]
                    if isinstance(operation, dict):
                        if 'security' in operation:
                            analysis['operations_with_security'] += 1
                        elif analysis['global_security']:
                            analysis['operations_with_security'] += 1
                        else:
                            analysis['operations_without_security'] += 1
        
        return analysis
    
    def analyze_complexity(self) -> Dict[str, Any]:
        """
        Analyze the overall complexity of the specification.
        
        Returns:
            Dictionary with complexity metrics
        """
        # Calculate various complexity metrics
        paths_analysis = self.analyze_paths()
        components_analysis = self.analyze_components()
        
        # Estimate complexity score (0-100)
        complexity_score = 0
        
        # Factor in number of operations
        operations = paths_analysis['total_operations']
        if operations > 100:
            complexity_score += 30
        elif operations > 50:
            complexity_score += 20
        elif operations > 20:
            complexity_score += 10
        else:
            complexity_score += 5
        
        # Factor in path depth
        avg_depth = paths_analysis['average_path_depth']
        if avg_depth > 4:
            complexity_score += 20
        elif avg_depth > 3:
            complexity_score += 15
        elif avg_depth > 2:
            complexity_score += 10
        else:
            complexity_score += 5
        
        # Factor in components
        total_components = sum(components_analysis['component_counts'].values())
        if total_components > 100:
            complexity_score += 25
        elif total_components > 50:
            complexity_score += 20
        elif total_components > 20:
            complexity_score += 15
        else:
            complexity_score += 10
        
        # Factor in reusability (inverse - less reuse = more complexity)
        reusability = components_analysis.get('reusability_score', 0)
        complexity_score += int((1 - reusability) * 25)
        
        # Normalize to 0-100
        complexity_score = min(100, complexity_score)
        
        return {
            'complexity_score': complexity_score,
            'complexity_level': (
                'Low' if complexity_score < 30 
                else 'Medium' if complexity_score < 70 
                else 'High'
            ),
            'total_operations': operations,
            'total_components': total_components,
            'average_path_depth': avg_depth,
            'reusability_score': reusability
        }
    
    def validate(self) -> Dict[str, Any]:
        """
        Validate the specification structure.
        
        Returns:
            Dictionary with validation results
        """
        issues = validate_spec_structure(self.spec)
        
        return {
            'is_valid': len(issues) == 0,
            'issue_count': len(issues),
            'issues': issues
        }
    
    def generate_full_analysis(self) -> Dict[str, Any]:
        """
        Generate a comprehensive analysis of the specification.
        
        Returns:
            Dictionary with full analysis results
        """
        logger.info("Generating full specification analysis...")
        
        analysis = {
            'basic_info': self.get_basic_info(),
            'paths': self.analyze_paths(),
            'components': self.analyze_components(),
            'tags': self.analyze_tags(),
            'security': self.analyze_security(),
            'complexity': self.analyze_complexity(),
            'validation': self.validate()
        }
        
        # Add recommendations based on analysis
        analysis['recommendations'] = self.generate_recommendations(analysis)
        
        return analysis
    
    def generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """
        Generate recommendations based on the analysis.
        
        Args:
            analysis: Full analysis results
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Check for validation issues
        if not analysis['validation']['is_valid']:
            recommendations.append(f"Fix {analysis['validation']['issue_count']} validation issues")
        
        # Check for missing components
        if not analysis['components']['has_components']:
            recommendations.append("Consider extracting reusable components to reduce duplication")
        elif analysis['components'].get('unused_components', 0) > 0:
            recommendations.append(f"Remove {analysis['components']['unused_components']} unused components")
        
        # Check for untagged operations
        if analysis['tags']['untagged_operations'] > 0:
            recommendations.append(f"Add tags to {analysis['tags']['untagged_operations']} untagged operations")
        
        # Check for undefined tags
        if analysis['tags']['undefined_tags']:
            recommendations.append(f"Define {len(analysis['tags']['undefined_tags'])} undefined tags in the tags section")
        
        # Check for security
        if not analysis['security']['has_security']:
            recommendations.append("Add security definitions to protect your API")
        elif analysis['security']['operations_without_security'] > 0:
            recommendations.append(f"Add security to {analysis['security']['operations_without_security']} unprotected operations")
        
        # Check complexity
        if analysis['complexity']['complexity_score'] > 70:
            recommendations.append("Consider splitting this large spec into smaller, more manageable parts")
        
        # Check reusability
        if analysis['components'].get('reusability_score', 0) < 0.3:
            recommendations.append("Improve component reusability by extracting common patterns")
        
        return recommendations
    
    def print_summary(self, analysis: Optional[Dict[str, Any]] = None) -> None:
        """
        Print a human-readable summary of the analysis.
        
        Args:
            analysis: Analysis results (will generate if not provided)
        """
        if analysis is None:
            analysis = self.generate_full_analysis()
        
        print("\n" + "="*60)
        print(f"OpenAPI Specification Analysis")
        print("="*60)
        
        # Basic info
        info = analysis['basic_info']
        print(f"\nSpecification: {info['title']} v{info['version']}")
        print(f"OpenAPI Version: {info['openapi_version']}")
        print(f"File: {info['file_path']}")
        print(f"Size: {info['file_size']:,} bytes")
        
        # Paths
        paths = analysis['paths']
        print(f"\nPaths & Operations:")
        print(f"  Total Paths: {paths['total_paths']}")
        print(f"  Total Operations: {paths['total_operations']}")
        print(f"  Operations by Method:")
        for method, count in paths['operations_by_method'].items():
            print(f"    {method.upper()}: {count}")
        
        # Components
        components = analysis['components']
        if components['component_counts']:
            print(f"\nComponents:")
            for comp_type, count in components['component_counts'].items():
                print(f"  {comp_type}: {count}")
            print(f"  Reusability Score: {components['reusability_score']:.1%}")
        
        # Tags
        tags = analysis['tags']
        print(f"\nTags:")
        print(f"  Defined: {tags['defined_tags']}")
        print(f"  Used: {tags['used_tags']}")
        if tags['undefined_tags']:
            print(f"  Undefined: {', '.join(tags['undefined_tags'])}")
        
        # Security
        security = analysis['security']
        print(f"\nSecurity:")
        print(f"  Has Security: {'Yes' if security['has_security'] else 'No'}")
        if security['security_schemes']:
            print(f"  Schemes: {', '.join(security['security_schemes'])}")
        print(f"  Protected Operations: {security['operations_with_security']}")
        print(f"  Unprotected Operations: {security['operations_without_security']}")
        
        # Complexity
        complexity = analysis['complexity']
        print(f"\nComplexity:")
        print(f"  Score: {complexity['complexity_score']}/100 ({complexity['complexity_level']})")
        
        # Validation
        validation = analysis['validation']
        print(f"\nValidation:")
        print(f"  Valid: {'Yes' if validation['is_valid'] else 'No'}")
        if not validation['is_valid']:
            print(f"  Issues: {validation['issue_count']}")
            for issue in validation['issues'][:5]:  # Show first 5 issues
                print(f"    - {issue}")
        
        # Recommendations
        if analysis['recommendations']:
            print(f"\nRecommendations:")
            for i, rec in enumerate(analysis['recommendations'], 1):
                print(f"  {i}. {rec}")
        
        print("\n" + "="*60)