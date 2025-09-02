#!/usr/bin/env python3
"""Command-line interface for OpenAPI specification tools."""

import sys
import argparse
import json
from pathlib import Path
import logging

from splitter import OpenAPISplitter
from merger import OpenAPIMerger
from analyzer import OpenAPIAnalyzer
from core import logger


def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s' if not verbose else '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def cmd_split(args):
    """Handle the split command."""
    try:
        splitter = OpenAPISplitter(args.spec_file, args.output_dir)
        
        # Show analysis first
        if not args.quiet:
            analysis = splitter.analyze_spec()
            print(f"\nSpec Analysis:")
            print(f"  Total endpoints: {analysis['total_endpoints']}")
            print(f"  Total operations: {analysis['total_operations']}")
            print(f"  Total schemas: {analysis['total_schemas']}")
            print()
        
        # Perform split based on method
        if args.method == 'tags':
            result = splitter.split_by_tags()
        elif args.method == 'path':
            result = splitter.split_by_path_prefix(args.max_operations)
        else:  # size
            result = splitter.split_by_size(args.max_operations)
        
        if args.json_output:
            print(json.dumps(result, indent=2))
        
        return 0
        
    except Exception as e:
        logger.error(f"Split operation failed: {e}")
        return 1


def cmd_merge(args):
    """Handle the merge command."""
    try:
        merger = OpenAPIMerger(args.input_dir, args.output)
        
        # Determine output format from filename
        output_format = 'yaml' if args.output.endswith(('.yaml', '.yml')) else 'json'
        
        # Perform merge
        stats = merger.merge_all(
            conflict_strategy=args.conflict_strategy,
            output_format=output_format
        )
        
        # Validate if requested
        if args.validate:
            issues = merger.validate_merged_spec()
            if issues:
                print("\nValidation issues found:")
                for issue in issues:
                    print(f"  - {issue}")
            else:
                print("\nMerged spec is valid!")
        
        if args.json_output:
            print(json.dumps(stats, indent=2))
        
        return 0
        
    except Exception as e:
        logger.error(f"Merge operation failed: {e}")
        return 1


def cmd_analyze(args):
    """Handle the analyze command."""
    try:
        analyzer = OpenAPIAnalyzer(args.spec_file)
        
        if args.full:
            # Full analysis with all details
            analysis = analyzer.generate_full_analysis()
            
            if args.json_output:
                print(json.dumps(analysis, indent=2))
            else:
                analyzer.print_summary(analysis)
            
            # Save to file if requested
            if args.output:
                output_path = Path(args.output)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(analysis, f, indent=2)
                print(f"\nAnalysis saved to {output_path}")
        
        else:
            # Basic analysis only
            analysis = analyzer.generate_full_analysis()
            
            # Show specific section if requested
            if args.section:
                if args.section in analysis:
                    if args.json_output:
                        print(json.dumps(analysis[args.section], indent=2))
                    else:
                        print(f"\n{args.section.title()} Analysis:")
                        for key, value in analysis[args.section].items():
                            print(f"  {key}: {value}")
                else:
                    logger.error(f"Unknown section: {args.section}")
                    print(f"Available sections: {', '.join(analysis.keys())}")
                    return 1
            else:
                # Default summary
                analyzer.print_summary(analysis)
        
        return 0
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1


def cmd_validate(args):
    """Handle the validate command."""
    try:
        analyzer = OpenAPIAnalyzer(args.spec_file)
        validation = analyzer.validate()
        
        if args.json_output:
            print(json.dumps(validation, indent=2))
        else:
            if validation['is_valid']:
                print(f"✓ Specification is valid")
            else:
                print(f"✗ Specification has {validation['issue_count']} issue(s):")
                for issue in validation['issues']:
                    print(f"  - {issue}")
        
        return 0 if validation['is_valid'] else 1
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='OpenAPI Specification Tools - Split, merge, and analyze OpenAPI specs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Split a spec by tags
  %(prog)s split api.json --method tags
  
  # Split a spec by path prefix with max 50 operations per file
  %(prog)s split api.yaml --method path --max-operations 50
  
  # Merge split specs back together
  %(prog)s merge --input-dir split_specs --output merged.json
  
  # Analyze a specification
  %(prog)s analyze api.json --full
  
  # Validate a specification
  %(prog)s validate api.yaml
        """
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='Suppress informational output')
    parser.add_argument('--json-output', action='store_true',
                       help='Output results as JSON')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Split command
    split_parser = subparsers.add_parser('split', 
                                        help='Split a large OpenAPI spec into smaller files')
    split_parser.add_argument('spec_file', 
                            help='Path to the OpenAPI spec file (JSON or YAML)')
    split_parser.add_argument('--output-dir', default='split_specs',
                            help='Output directory for split files (default: split_specs)')
    split_parser.add_argument('--method', choices=['tags', 'path', 'size'], default='path',
                            help='Split method: by tags, by path prefix, or by size (default: path)')
    split_parser.add_argument('--max-operations', type=int, default=30,
                            help='Maximum operations per file for path/size methods (default: 30)')
    
    # Merge command
    merge_parser = subparsers.add_parser('merge', 
                                        help='Merge split OpenAPI specs back into one file')
    merge_parser.add_argument('--input-dir', default='split_specs',
                            help='Directory containing split files (default: split_specs)')
    merge_parser.add_argument('--output', default='merged_spec.json',
                            help='Output file path (default: merged_spec.json)')
    merge_parser.add_argument('--conflict-strategy', 
                            choices=['keep_first', 'keep_last', 'error'], 
                            default='keep_first',
                            help='How to handle component conflicts (default: keep_first)')
    merge_parser.add_argument('--validate', action='store_true',
                            help='Validate the merged specification')
    
    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', 
                                          help='Analyze an OpenAPI specification')
    analyze_parser.add_argument('spec_file', 
                              help='Path to the OpenAPI spec file')
    analyze_parser.add_argument('--full', action='store_true',
                              help='Show full detailed analysis')
    analyze_parser.add_argument('--section', 
                              choices=['basic_info', 'paths', 'components', 'tags', 
                                     'security', 'complexity', 'validation'],
                              help='Show specific analysis section')
    analyze_parser.add_argument('--output', 
                              help='Save analysis to JSON file')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', 
                                           help='Validate an OpenAPI specification')
    validate_parser.add_argument('spec_file', 
                                help='Path to the OpenAPI spec file')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.verbose if hasattr(args, 'verbose') else False)
    
    # Execute command
    if not args.command:
        parser.print_help()
        return 0
    
    # Route to appropriate command handler
    if args.command == 'split':
        return cmd_split(args)
    elif args.command == 'merge':
        return cmd_merge(args)
    elif args.command == 'analyze':
        return cmd_analyze(args)
    elif args.command == 'validate':
        return cmd_validate(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())