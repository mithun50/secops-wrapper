"""
Command line handlers and helpers for SecOps CLI
"""

import argparse
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from secops import SecOpsClient
from secops.chronicle.data_table import DataTableColumnType
from secops.chronicle.reference_list import (
    ReferenceListSyntaxType,
    ReferenceListView,
)
from secops.exceptions import APIError, AuthenticationError, SecOpsError

# Define config directory and file paths
CONFIG_DIR = Path.home() / ".secops"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> Dict[str, Any]:
    """Load configuration from config file.

    Returns:
        Dictionary containing configuration values
    """
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print(
            f"Warning: Failed to load config from {CONFIG_FILE}",
            file=sys.stderr,
        )
        return {}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to config file.

    Args:
        config: Dictionary containing configuration values to save
    """
    # Create config directory if it doesn't exist
    CONFIG_DIR.mkdir(exist_ok=True)

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except IOError as e:
        print(
            f"Error: Failed to save config to {CONFIG_FILE}: {e}",
            file=sys.stderr,
        )


def setup_config_command(subparsers):
    """Set up the config command parser.

    Args:
        subparsers: Subparsers object to add to
    """
    config_parser = subparsers.add_parser(
        "config", help="Manage CLI configuration"
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", help="Config command"
    )

    # Set config command
    set_parser = config_subparsers.add_parser(
        "set", help="Set configuration values"
    )
    set_parser.add_argument(
        "--customer-id",
        "--customer_id",
        dest="customer_id",
        help="Chronicle instance ID",
    )
    set_parser.add_argument(
        "--project-id", "--project_id", dest="project_id", help="GCP project ID"
    )
    set_parser.add_argument("--region", help="Chronicle API region")
    set_parser.add_argument(
        "--service-account",
        "--service_account",
        dest="service_account",
        help="Path to service account JSON file",
    )
    set_parser.add_argument(
        "--start-time",
        "--start_time",
        dest="start_time",
        help="Default start time in ISO format (YYYY-MM-DDTHH:MM:SSZ)",
    )
    set_parser.add_argument(
        "--end-time",
        "--end_time",
        dest="end_time",
        help="Default end time in ISO format (YYYY-MM-DDTHH:MM:SSZ)",
    )
    set_parser.add_argument(
        "--time-window",
        "--time_window",
        dest="time_window",
        type=int,
        help="Default time window in hours",
    )
    set_parser.set_defaults(func=handle_config_set_command)

    # View config command
    view_parser = config_subparsers.add_parser(
        "view", help="View current configuration"
    )
    view_parser.set_defaults(func=handle_config_view_command)

    # Clear config command
    clear_parser = config_subparsers.add_parser(
        "clear", help="Clear current configuration"
    )
    clear_parser.set_defaults(func=handle_config_clear_command)


def handle_config_set_command(args, chronicle=None):
    """Handle config set command.

    Args:
        args: Command line arguments
        chronicle: Not used for this command
    """
    config = load_config()

    # Update config with new values
    if args.customer_id:
        config["customer_id"] = args.customer_id
    if args.project_id:
        config["project_id"] = args.project_id
    if args.region:
        config["region"] = args.region
    if args.service_account:
        config["service_account"] = args.service_account
    if args.start_time:
        config["start_time"] = args.start_time
    if args.end_time:
        config["end_time"] = args.end_time
    if args.time_window is not None:
        config["time_window"] = args.time_window

    save_config(config)
    print(f"Configuration saved to {CONFIG_FILE}")

    # Unused argument
    _ = (chronicle,)


def handle_config_view_command(args, chronicle=None):
    """Handle config view command.

    Args:
        args: Command line arguments
        chronicle: Not used for this command
    """
    config = load_config()

    if not config:
        print("No configuration found.")
        return

    print("Current configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")

    # Unused arguments
    _ = (args, chronicle)


def handle_config_clear_command(args, chronicle=None):
    """Handle config clear command.

    Args:
        args: Command line arguments
        chronicle: Not used for this command
    """
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        print("Configuration cleared.")
    else:
        print("No configuration found.")

    # Unused arguments
    _ = (args, chronicle)


def parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string in ISO format.

    Args:
        dt_str: ISO formatted datetime string

    Returns:
        Parsed datetime object
    """
    if not dt_str:
        return None
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def setup_client(args: argparse.Namespace) -> Tuple[SecOpsClient, Any]:
    """Set up and return SecOpsClient and Chronicle client based on args.

    Args:
        args: Command line arguments

    Returns:
        Tuple of (SecOpsClient, Chronicle client)
    """
    # Authentication setup
    client_kwargs = {}
    if args.service_account:
        client_kwargs["service_account_path"] = args.service_account

    # Create client
    try:
        client = SecOpsClient(**client_kwargs)

        # Initialize Chronicle client if required
        if (
            hasattr(args, "customer_id")
            or hasattr(args, "project_id")
            or hasattr(args, "region")
        ):
            chronicle_kwargs = {}
            if hasattr(args, "customer_id") and args.customer_id:
                chronicle_kwargs["customer_id"] = args.customer_id
            if hasattr(args, "project_id") and args.project_id:
                chronicle_kwargs["project_id"] = args.project_id
            if hasattr(args, "region") and args.region:
                chronicle_kwargs["region"] = args.region

            # Check if required args for Chronicle client are present
            missing_args = []
            if not chronicle_kwargs.get("customer_id"):
                missing_args.append("customer_id")
            if not chronicle_kwargs.get("project_id"):
                missing_args.append("project_id")

            if missing_args:
                print(
                    "Error: Missing required configuration parameters:",
                    ", ".join(missing_args),
                    file=sys.stderr,
                )
                print(
                    "\nPlease run the config command to set up your "
                    "configuration:",
                    file=sys.stderr,
                )
                print(
                    "  secops config set --customer-id YOUR_CUSTOMER_ID "
                    "--project-id YOUR_PROJECT_ID",
                    file=sys.stderr,
                )
                print(
                    "\nOr provide them as command-line options:",
                    file=sys.stderr,
                )
                print(
                    "  secops --customer-id YOUR_CUSTOMER_ID --project-id "
                    "YOUR_PROJECT_ID [command]",
                    file=sys.stderr,
                )
                print("\nFor help finding these values, run:", file=sys.stderr)
                print("  secops help --topic customer-id", file=sys.stderr)
                print("  secops help --topic project-id", file=sys.stderr)
                sys.exit(1)

            chronicle = client.chronicle(**chronicle_kwargs)
            return client, chronicle

        return client, None
    except (AuthenticationError, SecOpsError) as e:
        print(f"Authentication error: {e}", file=sys.stderr)
        print("\nFor configuration help, run:", file=sys.stderr)
        print("  secops help --topic config", file=sys.stderr)
        sys.exit(1)


def output_formatter(data: Any, output_format: str = "json") -> None:
    """Format and print output data.

    Args:
        data: Data to output
        output_format: Output format (json, text, table)
    """
    if output_format == "json":
        print(json.dumps(data, indent=2, default=str))
    elif output_format == "text":
        if isinstance(data, dict):
            for key, value in data.items():
                print(f"{key}: {value}")
        elif isinstance(data, list):
            for item in data:
                print(item)
        else:
            print(data)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments to a parser.

    Args:
        parser: Parser to add arguments to
    """
    config = load_config()

    parser.add_argument(
        "--service-account",
        "--service_account",
        dest="service_account",
        default=config.get("service_account"),
        help="Path to service account JSON file",
    )
    parser.add_argument(
        "--output",
        choices=["json", "text"],
        default="json",
        help="Output format",
    )


def add_chronicle_args(parser: argparse.ArgumentParser) -> None:
    """Add Chronicle-specific arguments to a parser.

    Args:
        parser: Parser to add arguments to
    """
    config = load_config()

    parser.add_argument(
        "--customer-id",
        "--customer_id",
        dest="customer_id",
        default=config.get("customer_id"),
        help="Chronicle instance ID",
    )
    parser.add_argument(
        "--project-id",
        "--project_id",
        dest="project_id",
        default=config.get("project_id"),
        help="GCP project ID",
    )
    parser.add_argument(
        "--region",
        default=config.get("region", "us"),
        help="Chronicle API region",
    )


def add_time_range_args(parser: argparse.ArgumentParser) -> None:
    """Add time range arguments to a parser.

    Args:
        parser: Parser to add arguments to
    """
    config = load_config()

    parser.add_argument(
        "--start-time",
        "--start_time",
        dest="start_time",
        default=config.get("start_time"),
        help="Start time in ISO format (YYYY-MM-DDTHH:MM:SSZ)",
    )
    parser.add_argument(
        "--end-time",
        "--end_time",
        dest="end_time",
        default=config.get("end_time"),
        help="End time in ISO format (YYYY-MM-DDTHH:MM:SSZ)",
    )
    parser.add_argument(
        "--time-window",
        "--time_window",
        dest="time_window",
        type=int,
        default=config.get("time_window", 24),
        help="Time window in hours (alternative to start/end time)",
    )


def get_time_range(args: argparse.Namespace) -> Tuple[datetime, datetime]:
    """Get start and end time from arguments.

    Args:
        args: Command line arguments

    Returns:
        Tuple of (start_time, end_time)
    """
    end_time = (
        parse_datetime(args.end_time)
        if args.end_time
        else datetime.now(timezone.utc)
    )

    if args.start_time:
        start_time = parse_datetime(args.start_time)
    else:
        start_time = end_time - timedelta(hours=args.time_window)

    return start_time, end_time


def setup_search_command(subparsers):
    """Set up the search command parser.

    Args:
        subparsers: Subparsers object to add to
    """
    search_parser = subparsers.add_parser("search", help="Search UDM events")
    search_parser.add_argument("--query", help="UDM query string")
    search_parser.add_argument(
        "--nl-query",
        "--nl_query",
        dest="nl_query",
        help="Natural language query",
    )
    search_parser.add_argument(
        "--max-events",
        "--max_events",
        dest="max_events",
        type=int,
        default=100,
        help="Maximum events to return",
    )
    search_parser.add_argument(
        "--fields",
        help="Comma-separated list of fields to include in CSV output",
    )
    search_parser.add_argument(
        "--csv", action="store_true", help="Output in CSV format"
    )
    add_time_range_args(search_parser)
    search_parser.set_defaults(func=handle_search_command)


def handle_search_command(args, chronicle):
    """Handle the search command.

    Args:
        args: Command line arguments
        chronicle: Chronicle client
    """
    start_time, end_time = get_time_range(args)

    try:
        if args.csv and args.fields:
            fields = [f.strip() for f in args.fields.split(",")]
            result = chronicle.fetch_udm_search_csv(
                query=args.query,
                start_time=start_time,
                end_time=end_time,
                fields=fields,
            )
            print(result)
        elif args.nl_query:
            result = chronicle.nl_search(
                text=args.nl_query,
                start_time=start_time,
                end_time=end_time,
                max_events=args.max_events,
            )
            output_formatter(result, args.output)
        else:
            result = chronicle.search_udm(
                query=args.query,
                start_time=start_time,
                end_time=end_time,
                max_events=args.max_events,
            )
            output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_stats_command(subparsers):
    """Set up the stats command parser."""
    stats_parser = subparsers.add_parser("stats", help="Get UDM statistics")
    stats_parser.add_argument(
        "--query", required=True, help="Stats query string"
    )
    stats_parser.add_argument(
        "--max-events",
        "--max_events",
        dest="max_events",
        type=int,
        default=1000,
        help="Maximum events to process",
    )
    stats_parser.add_argument(
        "--max-values",
        "--max_values",
        dest="max_values",
        type=int,
        default=100,
        help="Maximum values per field",
    )
    stats_parser.add_argument(
        "--timeout",
        dest="timeout",
        type=int,
        default=120,
        help="Timeout (in seconds) for API request",
    )
    add_time_range_args(stats_parser)
    stats_parser.set_defaults(func=handle_stats_command)


def handle_stats_command(args, chronicle):
    """Handle the stats command."""
    start_time, end_time = get_time_range(args)

    try:
        result = chronicle.get_stats(
            query=args.query,
            start_time=start_time,
            end_time=end_time,
            max_events=args.max_events,
            max_values=args.max_values,
            timeout=args.timeout,
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_entity_command(subparsers):
    """Set up the entity command parser."""
    entity_parser = subparsers.add_parser(
        "entity", help="Get entity information"
    )
    entity_parser.add_argument(
        "--value", required=True, help="Entity value (IP, domain, hash, etc.)"
    )
    entity_parser.add_argument(
        "--entity-type",
        "--entity_type",
        dest="entity_type",
        help="Entity type hint",
    )
    add_time_range_args(entity_parser)
    entity_parser.set_defaults(func=handle_entity_command)


def handle_entity_command(args, chronicle):
    """Handle the entity command."""
    start_time, end_time = get_time_range(args)

    try:
        result = chronicle.summarize_entity(
            value=args.value,
            start_time=start_time,
            end_time=end_time,
            preferred_entity_type=args.entity_type,
        )

        # Handle alert_counts properly - could be different types based on API
        alert_counts_list = []
        if result.alert_counts:
            for ac in result.alert_counts:
                # Try different methods to convert to dict
                try:
                    if hasattr(ac, "_asdict"):
                        alert_counts_list.append(ac._asdict())
                    elif hasattr(ac, "__dict__"):
                        alert_counts_list.append(vars(ac))
                    else:
                        # If it's already a dict or another type, just use it
                        alert_counts_list.append(ac)
                except Exception:  # pylint: disable=broad-exception-caught
                    # If all conversion attempts fail, use string representation
                    alert_counts_list.append(str(ac))

        # Safely handle prevalence data which may not be available for
        # all entity types
        prevalence_list = []
        if result.prevalence:
            try:
                prevalence_list = [vars(p) for p in result.prevalence]
            except (
                Exception  # pylint: disable=broad-exception-caught
            ) as prev_err:
                print(
                    f"Warning: Unable to process prevalence data: {prev_err}",
                    file=sys.stderr,
                )

        # Convert the EntitySummary to a dictionary for output
        result_dict = {
            "primary_entity": result.primary_entity,
            "related_entities": result.related_entities,
            "alert_counts": alert_counts_list,
            "timeline": vars(result.timeline) if result.timeline else None,
            "prevalence": prevalence_list,
        }
        output_formatter(result_dict, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        if "Unsupported artifact type" in str(e):
            print(
                f"Error: The entity type for '{args.value}' is not supported. "
                "Try specifying a different entity type with --entity-type.",
                file=sys.stderr,
            )
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_iocs_command(subparsers):
    """Set up the IOCs command parser."""
    iocs_parser = subparsers.add_parser("iocs", help="List IoCs")
    iocs_parser.add_argument(
        "--max-matches",
        "--max_matches",
        dest="max_matches",
        type=int,
        default=100,
        help="Maximum matches to return",
    )
    iocs_parser.add_argument(
        "--mandiant", action="store_true", help="Include Mandiant attributes"
    )
    iocs_parser.add_argument(
        "--prioritized",
        action="store_true",
        help="Only return prioritized IoCs",
    )
    add_time_range_args(iocs_parser)
    iocs_parser.set_defaults(func=handle_iocs_command)


def handle_iocs_command(args, chronicle):
    """Handle the IOCs command."""
    start_time, end_time = get_time_range(args)

    try:
        result = chronicle.list_iocs(
            start_time=start_time,
            end_time=end_time,
            max_matches=args.max_matches,
            add_mandiant_attributes=args.mandiant,
            prioritized_only=args.prioritized,
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_log_command(subparsers):
    """Set up the log command parser."""
    log_parser = subparsers.add_parser("log", help="Ingest logs")
    log_subparsers = log_parser.add_subparsers(
        dest="log_command", help="Log command"
    )

    # Ingest log command
    ingest_parser = log_subparsers.add_parser("ingest", help="Ingest raw logs")
    ingest_parser.add_argument("--type", required=True, help="Log type")
    ingest_parser.add_argument("--file", help="File containing log data")
    ingest_parser.add_argument(
        "--message", help="Log message (alternative to file)"
    )
    ingest_parser.add_argument(
        "--forwarder-id",
        "--forwarder_id",
        dest="forwarder_id",
        help="Custom forwarder ID",
    )
    ingest_parser.add_argument(
        "--force", action="store_true", help="Force unknown log type"
    )
    ingest_parser.add_argument(
        "--labels",
        help="JSON string or comma-separated key=value pairs for custom labels",
    )
    ingest_parser.set_defaults(func=handle_log_ingest_command)

    # Ingest UDM command
    udm_parser = log_subparsers.add_parser(
        "ingest-udm", help="Ingest UDM events"
    )
    udm_parser.add_argument(
        "--file", required=True, help="File containing UDM event(s)"
    )
    udm_parser.set_defaults(func=handle_udm_ingest_command)

    # List log types command
    types_parser = log_subparsers.add_parser(
        "types", help="List available log types"
    )
    types_parser.add_argument("--search", help="Search term for log types")
    types_parser.set_defaults(func=handle_log_types_command)


def handle_log_ingest_command(args, chronicle):
    """Handle log ingestion command."""
    try:
        log_message = args.message
        if args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                log_message = f.read()

        # Process labels if provided
        labels = None
        if args.labels:
            # Try parsing as JSON first
            try:
                labels = json.loads(args.labels)
            except json.JSONDecodeError:
                # If not valid JSON, try parsing as comma-separated
                # key=value pairs
                labels = {}
                for pair in args.labels.split(","):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        labels[key.strip()] = value.strip()
                    else:
                        print(
                            f"Warning: Ignoring invalid label format: {pair}",
                            file=sys.stderr,
                        )

                if not labels:
                    print(
                        "Warning: No valid labels found. Labels should be in "
                        "JSON format or comma-separated key=value pairs.",
                        file=sys.stderr,
                    )

        result = chronicle.ingest_log(
            log_type=args.type,
            log_message=log_message,
            forwarder_id=args.forwarder_id,
            force_log_type=args.force,
            labels=labels,
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_udm_ingest_command(args, chronicle):
    """Handle UDM ingestion command."""
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            udm_events = json.load(f)

        result = chronicle.ingest_udm(udm_events=udm_events)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_log_types_command(args, chronicle):
    """Handle listing log types command."""
    try:
        if args.search:
            result = chronicle.search_log_types(args.search)
        else:
            result = chronicle.get_all_log_types()

        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_parser_command(subparsers):
    """Set up the parser command parser."""

    parser_parser = subparsers.add_parser("parser", help="Manage Parsers")
    parser_subparsers = parser_parser.add_subparsers(
        dest="parser_command", help="Parser command"
    )

    # --- Activate Parser Command ---
    activate_parser_sub = parser_subparsers.add_parser(
        "activate", help="Activate a custom parser."
    )
    activate_parser_sub.add_argument(
        "--log-type", type=str, help="Log type of the parser."
    )
    activate_parser_sub.add_argument(
        "--id", type=str, help="ID of the parser to activate."
    )
    activate_parser_sub.set_defaults(func=handle_parser_activate_command)

    # --- Activate Release Candidate Parser Command ---
    activate_rc_parser_sub = parser_subparsers.add_parser(
        "activate-rc", help="Activate the release candidate parser."
    )
    activate_rc_parser_sub.add_argument(
        "--log-type", type=str, help="Log type of the parser."
    )
    activate_rc_parser_sub.add_argument(
        "--id", type=str, help="ID of the release candidate parser to activate."
    )
    activate_rc_parser_sub.set_defaults(func=handle_parser_activate_rc_command)

    # --- Copy Parser Command ---
    copy_parser_sub = parser_subparsers.add_parser(
        "copy", help="Make a copy of a prebuilt parser."
    )
    copy_parser_sub.add_argument(
        "--log-type", type=str, help="Log type of the parser to copy."
    )
    copy_parser_sub.add_argument(
        "--id", type=str, help="ID of the parser to copy."
    )
    copy_parser_sub.set_defaults(func=handle_parser_copy_command)

    # --- Create Parser Command ---
    create_parser_sub = parser_subparsers.add_parser(
        "create", help="Create a new parser."
    )
    create_parser_sub.add_argument(
        "--log-type", type=str, help="Log type for the new parser."
    )
    create_parser_code_group = create_parser_sub.add_mutually_exclusive_group(
        required=True
    )
    create_parser_code_group.add_argument(
        "--parser-code", type=str, help="Content of the new parser (CBN code)."
    )
    create_parser_code_group.add_argument(
        "--parser-code-file",
        type=str,
        help="Path to a file containing the parser code (CBN code).",
    )
    create_parser_sub.add_argument(
        "--validated-on-empty-logs",
        action="store_true",
        help=(
            "Whether the parser is validated on empty logs "
            "(default: True if not specified, only use flag for True)."
        ),
    )
    create_parser_sub.set_defaults(func=handle_parser_create_command)

    # --- Deactivate Parser Command ---
    deactivate_parser_sub = parser_subparsers.add_parser(
        "deactivate", help="Deactivate a custom parser."
    )
    deactivate_parser_sub.add_argument(
        "--log-type", type=str, help="Log type of the parser."
    )
    deactivate_parser_sub.add_argument(
        "--id", type=str, help="ID of the parser to deactivate."
    )
    deactivate_parser_sub.set_defaults(func=handle_parser_deactivate_command)

    # --- Delete Parser Command ---
    delete_parser_sub = parser_subparsers.add_parser(
        "delete", help="Delete a parser."
    )
    delete_parser_sub.add_argument(
        "--log-type", type=str, help="Log type of the parser."
    )
    delete_parser_sub.add_argument(
        "--id", type=str, help="ID of the parser to delete."
    )
    delete_parser_sub.add_argument(
        "--force",
        action="store_true",
        help="Forcefully delete an ACTIVE parser.",
    )
    delete_parser_sub.set_defaults(func=handle_parser_delete_command)

    # --- Get Parser Command ---
    get_parser_sub = parser_subparsers.add_parser(
        "get", help="Get a parser by ID."
    )
    get_parser_sub.add_argument(
        "--log-type", type=str, help="Log type of the parser."
    )
    get_parser_sub.add_argument(
        "--id", type=str, help="ID of the parser to retrieve."
    )
    get_parser_sub.set_defaults(func=handle_parser_get_command)

    # --- List Parsers Command ---
    list_parsers_sub = parser_subparsers.add_parser(
        "list", help="List parsers."
    )
    list_parsers_sub.add_argument(
        "--log-type",
        type=str,
        default="-",
        help="Log type to filter by (default: '-' for all).",
    )
    list_parsers_sub.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="The maximum number of parsers to return per page.",
    )
    list_parsers_sub.add_argument(
        "--page-token",
        type=str,
        help="A page token, received from a previous `list` call.",
    )
    list_parsers_sub.add_argument(
        "--filter",
        type=str,
        help="Filter expression to apply (e.g., 'state=ACTIVE').",
    )
    list_parsers_sub.set_defaults(func=handle_parser_list_command)

    # --- Run Parser Command ---
    run_parser_sub = parser_subparsers.add_parser(
        "run",
        help="Run parser against sample logs for evaluation.",
        description=(
            "Evaluate a parser by running it against sample log entries. "
            "This helps test parser logic before deploying it."
        ),
        epilog=(
            "Examples:\n"
            "  # Run parser with inline code and logs:\n"
            "  secops parser run --log-type OKTA --parser-code 'filter {}' "
            "--log 'log1' --log 'log2'\n\n"
            "  # Run parser using files:\n"
            "  secops parser run --log-type WINDOWS "
            "--parser-code-file parser.conf --logs-file logs.txt\n\n"
            "  # Run parser with the active parser\n"
            "  secops parser run --log-type OKTA --log-file logs.txt\n\n"
            "  # Run parser with extension:\n"
            "  secops parser run --log-type CUSTOM --parser-code-file "
            "parser.conf \\\n    --parser-extension-code-file extension.conf "
            "--logs-file logs.txt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser_sub.add_argument(
        "--log-type",
        type=str,
        required=True,
        help="Log type of the parser for evaluation (e.g., OKTA, WINDOWS_AD)",
    )
    run_parser_code_group = run_parser_sub.add_mutually_exclusive_group(
        required=False
    )
    run_parser_code_group.add_argument(
        "--parser-code",
        type=str,
        help="Content of the main parser (CBN code) to evaluate",
    )
    run_parser_code_group.add_argument(
        "--parser-code-file",
        type=str,
        help="Path to a file containing the main parser code (CBN code)",
    )
    run_parser_ext_group = run_parser_sub.add_mutually_exclusive_group(
        required=False
    )
    run_parser_ext_group.add_argument(
        "--parser-extension-code",
        type=str,
        help="Content of the parser extension (CBN snippet)",
    )
    run_parser_ext_group.add_argument(
        "--parser-extension-code-file",
        type=str,
        help=(
            "Path to a file containing the parser extension code (CBN snippet)"
        ),
    )
    run_parser_logs_group = run_parser_sub.add_mutually_exclusive_group(
        required=True
    )
    run_parser_logs_group.add_argument(
        "--log",
        action="append",
        help=(
            "Provide a raw log string to test. Can be specified multiple "
            "times for multiple logs"
        ),
    )
    run_parser_logs_group.add_argument(
        "--logs-file",
        type=str,
        help="Path to a file containing raw logs (one log per line)",
    )
    run_parser_sub.add_argument(
        "--statedump-allowed",
        action="store_true",
        help="Enable statedump filter for the parser configuration",
    )
    run_parser_sub.set_defaults(func=handle_parser_run_command)


def handle_parser_activate_command(args, chronicle):
    """Handle parser activate command."""
    try:
        result = chronicle.activate_parser(args.log_type, args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error activating parser: {e}", file=sys.stderr)
        sys.exit(1)


def handle_parser_activate_rc_command(args, chronicle):
    """Handle parser activate-release-candidate command."""
    try:
        result = chronicle.activate_release_candidate_parser(
            args.log_type, args.id
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(
            f"Error activating release candidate parser: {e}", file=sys.stderr
        )
        sys.exit(1)


def handle_parser_copy_command(args, chronicle):
    """Handle parser copy command."""
    try:
        result = chronicle.copy_parser(args.log_type, args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error copying parser: {e}", file=sys.stderr)
        sys.exit(1)


def handle_parser_create_command(args, chronicle):
    """Handle parser create command."""
    try:
        parser_code = ""
        if args.parser_code_file:
            try:
                with open(args.parser_code_file, "r", encoding="utf-8") as f:
                    parser_code = f.read()
            except IOError as e:
                print(f"Error reading parser code file: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.parser_code:
            parser_code = args.parser_code
        else:
            raise SecOpsError(
                "Either --parser-code or --parser-code-file must be provided."
            )

        result = chronicle.create_parser(
            args.log_type, parser_code, args.validated_on_empty_logs
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error creating parser: {e}", file=sys.stderr)
        sys.exit(1)


def handle_parser_deactivate_command(args, chronicle):
    """Handle parser deactivate command."""
    try:
        result = chronicle.deactivate_parser(args.log_type, args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error deactivating parser: {e}", file=sys.stderr)
        sys.exit(1)


def handle_parser_delete_command(args, chronicle):
    """Handle parser delete command."""
    try:
        result = chronicle.delete_parser(args.log_type, args.id, args.force)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error deleting parser: {e}", file=sys.stderr)
        sys.exit(1)


def handle_parser_get_command(args, chronicle):
    """Handle parser get command."""
    try:
        result = chronicle.get_parser(args.log_type, args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error getting parser: {e}", file=sys.stderr)
        sys.exit(1)


def handle_parser_list_command(args, chronicle):
    """Handle parser list command."""
    try:
        result = chronicle.list_parsers(
            args.log_type, args.page_size, args.page_token, args.filter
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error listing parsers: {e}", file=sys.stderr)
        sys.exit(1)


def handle_parser_run_command(args, chronicle):
    """Handle parser run (evaluation) command."""
    try:
        # Read parser code
        parser_code = ""
        if args.parser_code_file:
            try:
                with open(args.parser_code_file, "r", encoding="utf-8") as f:
                    parser_code = f.read()
            except IOError as e:
                print(f"Error reading parser code file: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.parser_code:
            parser_code = args.parser_code
        else:
            # If no parser code provided,
            # try to find an active parser for the log type
            parsers = chronicle.list_parsers(
                args.log_type,
                page_size=1,
                page_token=None,
                filter="STATE=ACTIVE",
            )
            if len(parsers) < 1:
                raise SecOpsError(
                    "No parser file provided and an active parser could not "
                    f"be found for log type '{args.log_type}'."
                )
            parser_code_encoded = parsers[0].get("cbn")
            parser_code = base64.b64decode(parser_code_encoded).decode("utf-8")

        # Read parser extension code (optional)
        parser_extension_code = ""
        if args.parser_extension_code_file:
            try:
                with open(
                    args.parser_extension_code_file, "r", encoding="utf-8"
                ) as f:
                    parser_extension_code = f.read()
            except IOError as e:
                print(
                    f"Error reading parser extension code file: {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
        elif args.parser_extension_code:
            parser_extension_code = args.parser_extension_code

        # Read logs
        logs = []
        if args.logs_file:
            try:
                with open(args.logs_file, "r", encoding="utf-8") as f:
                    logs = [line.strip() for line in f if line.strip()]
            except IOError as e:
                print(f"Error reading logs file: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.log:
            logs = args.log

        if not logs:
            print(
                "Error: No logs provided. Use --log or --logs-file to provide "
                "log entries.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Call the API
        result = chronicle.run_parser(
            args.log_type,
            parser_code,
            parser_extension_code,
            logs,
            args.statedump_allowed,
        )

        output_formatter(result, args.output)

    except ValueError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except APIError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error running parser: {e}", file=sys.stderr)
        sys.exit(1)


def setup_feed_command(subparsers):
    """Set up the feed command parser."""
    feed_parser = subparsers.add_parser("feed", help="Manage feeds")
    feed_subparsers = feed_parser.add_subparsers(
        dest="feed_command", help="Feed command"
    )

    # List feeds command
    list_parser = feed_subparsers.add_parser("list", help="List feeds")
    list_parser.set_defaults(func=handle_feed_list_command)

    # Get feed command
    get_parser = feed_subparsers.add_parser("get", help="Get feed details")
    get_parser.add_argument("--id", required=True, help="Feed ID")
    get_parser.set_defaults(func=handle_feed_get_command)

    # Create feed command
    create_parser = feed_subparsers.add_parser("create", help="Create a feed")
    create_parser.add_argument(
        "--display-name", required=True, help="Feed display name"
    )
    create_parser.add_argument(
        "--details", required=True, help="Feed details as JSON string"
    )
    create_parser.set_defaults(func=handle_feed_create_command)

    # Update feed command
    update_parser = feed_subparsers.add_parser("update", help="Update a feed")
    update_parser.add_argument("--id", required=True, help="Feed ID")
    update_parser.add_argument(
        "--display-name", required=False, help="Feed display name"
    )
    update_parser.add_argument(
        "--details", required=False, help="Feed details as JSON string"
    )
    update_parser.set_defaults(func=handle_feed_update_command)

    # Delete feed command
    delete_parser = feed_subparsers.add_parser("delete", help="Delete a feed")
    delete_parser.add_argument("--id", required=True, help="Feed ID")
    delete_parser.set_defaults(func=handle_feed_delete_command)

    # Enable feed command
    enable_parser = feed_subparsers.add_parser("enable", help="Enable a feed")
    enable_parser.add_argument("--id", required=True, help="Feed ID")
    enable_parser.set_defaults(func=handle_feed_enable_command)

    # Disable feed command
    disable_parser = feed_subparsers.add_parser(
        "disable", help="Disable a feed"
    )
    disable_parser.add_argument("--id", required=True, help="Feed ID")
    disable_parser.set_defaults(func=handle_feed_disable_command)

    # Generate secret command
    generate_secret_parser = feed_subparsers.add_parser(
        "generate-secret", help="Generate a secret for a feed"
    )
    generate_secret_parser.add_argument("--id", required=True, help="Feed ID")
    generate_secret_parser.set_defaults(
        func=handle_feed_generate_secret_command
    )


def handle_feed_list_command(args, chronicle):
    """Handle feed list command."""
    try:
        result = chronicle.list_feeds()
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_feed_get_command(args, chronicle):
    """Handle feed get command."""
    try:
        result = chronicle.get_feed(args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_feed_create_command(args, chronicle):
    """Handle feed create command."""
    try:
        result = chronicle.create_feed(args.display_name, args.details)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_feed_update_command(args, chronicle):
    """Handle feed update command."""
    try:
        result = chronicle.update_feed(args.id, args.display_name, args.details)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_feed_delete_command(args, chronicle):
    """Handle feed delete command."""
    try:
        result = chronicle.delete_feed(args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_feed_enable_command(args, chronicle):
    """Handle feed enable command."""
    try:
        result = chronicle.enable_feed(args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_feed_disable_command(args, chronicle):
    """Handle feed disable command."""
    try:
        result = chronicle.disable_feed(args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_feed_generate_secret_command(args, chronicle):
    """Handle feed generate secret command."""
    try:
        result = chronicle.generate_secret(args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_rule_command(subparsers):
    """Set up the rule command parser."""
    rule_parser = subparsers.add_parser("rule", help="Manage detection rules")
    rule_subparsers = rule_parser.add_subparsers(
        dest="rule_command", help="Rule command"
    )

    # List rules command
    list_parser = rule_subparsers.add_parser("list", help="List rules")
    list_parser.set_defaults(func=handle_rule_list_command)

    # Get rule command
    get_parser = rule_subparsers.add_parser("get", help="Get rule details")
    get_parser.add_argument("--id", required=True, help="Rule ID")
    get_parser.set_defaults(func=handle_rule_get_command)

    # Create rule command
    create_parser = rule_subparsers.add_parser("create", help="Create a rule")
    create_parser.add_argument(
        "--file", required=True, help="File containing rule text"
    )
    create_parser.set_defaults(func=handle_rule_create_command)

    # Update rule command
    update_parser = rule_subparsers.add_parser("update", help="Update a rule")
    update_parser.add_argument("--id", required=True, help="Rule ID")
    update_parser.add_argument(
        "--file", required=True, help="File containing updated rule text"
    )
    update_parser.set_defaults(func=handle_rule_update_command)

    # Enable/disable rule command
    enable_parser = rule_subparsers.add_parser(
        "enable", help="Enable or disable a rule"
    )
    enable_parser.add_argument("--id", required=True, help="Rule ID")
    enable_parser.add_argument(
        "--enabled",
        choices=["true", "false"],
        required=True,
        help="Enable or disable the rule",
    )
    enable_parser.set_defaults(func=handle_rule_enable_command)

    # Delete rule command
    delete_parser = rule_subparsers.add_parser("delete", help="Delete a rule")
    delete_parser.add_argument("--id", required=True, help="Rule ID")
    delete_parser.add_argument(
        "--force",
        action="store_true",
        help="Force deletion of rule with retrohunts",
    )
    delete_parser.set_defaults(func=handle_rule_delete_command)

    # Validate rule command
    validate_parser = rule_subparsers.add_parser(
        "validate", help="Validate a rule"
    )
    validate_parser.add_argument(
        "--file", required=True, help="File containing rule text"
    )
    validate_parser.set_defaults(func=handle_rule_validate_command)

    # Test rule command
    test_parser = rule_subparsers.add_parser(
        "test", help="Test a rule against historical data"
    )
    test_parser.add_argument(
        "--file", required=True, help="File containing rule text"
    )
    test_parser.add_argument(
        "--max-results",
        "--max_results",
        dest="max_results",
        type=int,
        default=100,
        help="Maximum results to return (1-10000, default 100)",
    )
    add_time_range_args(test_parser)
    test_parser.set_defaults(func=handle_rule_test_command)

    # Search rules command
    search_parser = rule_subparsers.add_parser("search", help="Search rules")
    search_parser.set_defaults(func=handle_rule_search_command)
    search_parser.add_argument(
        "--query", required=True, help="Rule query string in regex"
    )


def handle_rule_list_command(args, chronicle):
    """Handle rule list command."""
    try:
        result = chronicle.list_rules()
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rule_get_command(args, chronicle):
    """Handle rule get command."""
    try:
        result = chronicle.get_rule(args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rule_create_command(args, chronicle):
    """Handle rule create command."""
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            rule_text = f.read()

        result = chronicle.create_rule(rule_text)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rule_update_command(args, chronicle):
    """Handle rule update command."""
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            rule_text = f.read()

        result = chronicle.update_rule(args.id, rule_text)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rule_enable_command(args, chronicle):
    """Handle rule enable/disable command."""
    try:
        enabled = args.enabled.lower() == "true"
        result = chronicle.enable_rule(args.id, enabled=enabled)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rule_delete_command(args, chronicle):
    """Handle rule delete command."""
    try:
        result = chronicle.delete_rule(args.id, force=args.force)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rule_validate_command(args, chronicle):
    """Handle rule validate command."""
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            rule_text = f.read()

        result = chronicle.validate_rule(rule_text)
        if result.success:
            print("Rule is valid.")
        else:
            print(f"Rule is invalid: {result.message}")
            if result.position:
                print(
                    f'Error at line {result.position["startLine"]}, '
                    f'column {result.position["startColumn"]}'
                )
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rule_test_command(args, chronicle):
    """Handle rule test command.

    This command tests a rule against historical data and outputs UDM events
    as JSON objects.
    """
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            rule_text = f.read()

        start_time, end_time = get_time_range(args)

        # Process streaming results
        all_events = []

        for result in chronicle.run_rule_test(
            rule_text, start_time, end_time, max_results=args.max_results
        ):
            if result.get("type") == "detection":
                detection = result.get("detection", {})
                result_events = detection.get("resultEvents", {})

                # Extract UDM events from resultEvents structure
                # resultEvents is an object with variable names as
                # keys (from the rule) and each variable contains an
                # eventSamples array with the actual events
                for _, event_data in result_events.items():
                    if (
                        isinstance(event_data, dict)
                        and "eventSamples" in event_data
                    ):
                        for sample in event_data.get("eventSamples", []):
                            if "event" in sample:
                                # Extract the actual UDM event
                                udm_event = sample.get("event")
                                all_events.append(udm_event)

        # Output all events as a single JSON array
        print(json.dumps(all_events))

    except APIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

    return 0


def handle_rule_search_command(args, chronicle):
    """Handle rule search command."""
    try:
        result = chronicle.search_rules(args.query)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_alert_command(subparsers):
    """Set up the alert command parser."""
    alert_parser = subparsers.add_parser("alert", help="Manage alerts")
    alert_parser.add_argument(
        "--snapshot-query",
        "--snapshot_query",
        dest="snapshot_query",
        help=(
            'Query to filter alerts (e.g. feedback_summary.status != "CLOSED")'
        ),
    )
    alert_parser.add_argument(
        "--baseline-query",
        "--baseline_query",
        dest="baseline_query",
        help="Baseline query for alerts",
    )
    alert_parser.add_argument(
        "--max-alerts",
        "--max_alerts",
        dest="max_alerts",
        type=int,
        default=100,
        help="Maximum alerts to return",
    )
    add_time_range_args(alert_parser)
    alert_parser.set_defaults(func=handle_alert_command)


def handle_alert_command(args, chronicle):
    """Handle alert command."""
    start_time, end_time = get_time_range(args)

    try:
        result = chronicle.get_alerts(
            start_time=start_time,
            end_time=end_time,
            snapshot_query=args.snapshot_query,
            baseline_query=args.baseline_query,
            max_alerts=args.max_alerts,
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_case_command(subparsers):
    """Set up the case command parser."""
    case_parser = subparsers.add_parser("case", help="Manage cases")
    case_parser.add_argument("--ids", help="Comma-separated list of case IDs")
    case_parser.set_defaults(func=handle_case_command)


def handle_case_command(args, chronicle):
    """Handle case command."""
    try:
        if args.ids:
            case_ids = [id.strip() for id in args.ids.split(",")]
            result = chronicle.get_cases(case_ids)

            # Convert CaseList to dictionary for output
            cases_dict = {
                "cases": [
                    {
                        "id": case.id,
                        "display_name": case.display_name,
                        "stage": case.stage,
                        "priority": case.priority,
                        "status": case.status,
                        "soar_platform_info": (
                            {
                                "case_id": case.soar_platform_info.case_id,
                                "platform_type": case.soar_platform_info.platform_type,  # pylint: disable=line-too-long
                            }
                            if case.soar_platform_info
                            else None
                        ),
                        "alert_ids": case.alert_ids,
                    }
                    for case in result.cases
                ]
            }
            output_formatter(cases_dict, args.output)
        else:
            print("Error: No case IDs provided", file=sys.stderr)
            sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_export_command(subparsers):
    """Set up the data export command parser."""
    export_parser = subparsers.add_parser("export", help="Manage data exports")
    export_subparsers = export_parser.add_subparsers(
        dest="export_command", help="Export command"
    )

    # List available log types command
    log_types_parser = export_subparsers.add_parser(
        "log-types", help="List available log types for export"
    )
    add_time_range_args(log_types_parser)
    log_types_parser.add_argument(
        "--page-size",
        "--page_size",
        dest="page_size",
        type=int,
        default=100,
        help="Page size for results",
    )
    log_types_parser.set_defaults(func=handle_export_log_types_command)

    # Create export command
    create_parser = export_subparsers.add_parser(
        "create", help="Create a data export"
    )
    create_parser.add_argument(
        "--gcs-bucket",
        "--gcs_bucket",
        dest="gcs_bucket",
        required=True,
        help="GCS bucket in format 'projects/PROJECT_ID/buckets/BUCKET_NAME'",
    )
    create_parser.add_argument(
        "--log-type", "--log_type", dest="log_type", help="Log type to export"
    )
    create_parser.add_argument(
        "--all-logs",
        "--all_logs",
        dest="all_logs",
        action="store_true",
        help="Export all log types",
    )
    add_time_range_args(create_parser)
    create_parser.set_defaults(func=handle_export_create_command)

    # Get export status command
    status_parser = export_subparsers.add_parser(
        "status", help="Get export status"
    )
    status_parser.add_argument("--id", required=True, help="Export ID")
    status_parser.set_defaults(func=handle_export_status_command)

    # Cancel export command
    cancel_parser = export_subparsers.add_parser(
        "cancel", help="Cancel an export"
    )
    cancel_parser.add_argument("--id", required=True, help="Export ID")
    cancel_parser.set_defaults(func=handle_export_cancel_command)


def handle_export_log_types_command(args, chronicle):
    """Handle export log types command."""
    start_time, end_time = get_time_range(args)

    try:
        result = chronicle.fetch_available_log_types(
            start_time=start_time, end_time=end_time, page_size=args.page_size
        )

        # Convert to a simple dict for output
        log_types_dict = {
            "log_types": [
                {
                    "log_type": lt.log_type.split("/")[-1],
                    "display_name": lt.display_name,
                    "start_time": lt.start_time.isoformat(),
                    "end_time": lt.end_time.isoformat(),
                }
                for lt in result["available_log_types"]
            ],
            "next_page_token": result.get("next_page_token", ""),
        }

        output_formatter(log_types_dict, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_export_create_command(args, chronicle):
    """Handle export create command."""
    start_time, end_time = get_time_range(args)

    try:
        # First, try to fetch available log types to see if there are any
        available_logs = chronicle.fetch_available_log_types(
            start_time=start_time, end_time=end_time
        )

        if not available_logs.get("available_log_types") and not args.log_type:
            print(
                "Warning: No log types are available for export in "
                "the specified time range.",
                file=sys.stderr,
            )
            print(
                "You may need to adjust your time range or check your "
                "Chronicle instance configuration.",
                file=sys.stderr,
            )
            if args.all_logs:
                print(
                    "Creating export with --all-logs flag anyway...",
                    file=sys.stderr,
                )
            else:
                print(
                    "Error: Cannot create export without specifying a log type "
                    "when no log types are available.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # If log_type is specified, check if it exists in available log types
        if args.log_type and available_logs.get("available_log_types"):
            log_type_found = False
            for lt in available_logs.get("available_log_types", []):
                if lt.log_type.endswith(
                    "/" + args.log_type
                ) or lt.log_type.endswith("/logTypes/" + args.log_type):
                    log_type_found = True
                    break

            if not log_type_found:
                print(
                    f"Warning: Log type '{args.log_type}' not found in "
                    "available log types.",
                    file=sys.stderr,
                )
                print("Available log types:", file=sys.stderr)
                for lt in available_logs.get("available_log_types", [])[
                    :5
                ]:  # Show first 5
                    print(f'  {lt.log_type.split("/")[-1]}', file=sys.stderr)
                print("Attempting to create export anyway...", file=sys.stderr)

        # Proceed with export creation
        if args.all_logs:
            result = chronicle.create_data_export(
                gcs_bucket=args.gcs_bucket,
                start_time=start_time,
                end_time=end_time,
                export_all_logs=True,
            )
        elif args.log_type:
            result = chronicle.create_data_export(
                gcs_bucket=args.gcs_bucket,
                start_time=start_time,
                end_time=end_time,
                log_type=args.log_type,
            )
        else:
            print(
                "Error: Either --log-type or --all-logs must be specified",
                file=sys.stderr,
            )
            sys.exit(1)

        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        error_msg = str(e)
        print(f"Error: {error_msg}", file=sys.stderr)

        # Provide helpful advice based on common errors
        if "unrecognized log type" in error_msg.lower():
            print("\nPossible solutions:", file=sys.stderr)
            print(
                "1. Verify the log type exists in your Chronicle instance",
                file=sys.stderr,
            )
            print(
                "2. Try using 'secops export log-types' to see "
                "available log types",
                file=sys.stderr,
            )
            print(
                "3. Check if your time range contains data for this log type",
                file=sys.stderr,
            )
            print(
                "4. Make sure your GCS bucket is properly formatted as "
                "'projects/PROJECT_ID/buckets/BUCKET_NAME'",
                file=sys.stderr,
            )
        elif (
            "permission" in error_msg.lower()
            or "unauthorized" in error_msg.lower()
        ):
            print(
                "\nPossible authentication or permission issues:",
                file=sys.stderr,
            )
            print(
                "1. Verify your credentials have access to Chronicle and the "
                "specified GCS bucket",
                file=sys.stderr,
            )
            print(
                "2. Check if your service account has the required IAM roles",
                file=sys.stderr,
            )

        sys.exit(1)


def handle_export_status_command(args, chronicle):
    """Handle export status command."""
    try:
        result = chronicle.get_data_export(args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_export_cancel_command(args, chronicle):
    """Handle export cancel command."""
    try:
        result = chronicle.cancel_data_export(args.id)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_gemini_command(subparsers):
    """Set up the Gemini command parser."""
    gemini_parser = subparsers.add_parser(
        "gemini", help="Interact with Gemini AI"
    )
    gemini_parser.add_argument(
        "--query", required=True, help="Query for Gemini"
    )
    gemini_parser.add_argument(
        "--conversation-id",
        "--conversation_id",
        dest="conversation_id",
        help="Continue an existing conversation",
    )
    gemini_parser.add_argument(
        "--raw", action="store_true", help="Output raw API response"
    )
    gemini_parser.add_argument(
        "--opt-in",
        "--opt_in",
        dest="opt_in",
        action="store_true",
        help="Explicitly opt-in to Gemini",
    )
    gemini_parser.set_defaults(func=handle_gemini_command)


def handle_gemini_command(args, chronicle):
    """Handle Gemini command."""
    try:
        if args.opt_in:
            result = chronicle.opt_in_to_gemini()
            print(f'Opt-in result: {"Success" if result else "Failed"}')
            if not result:
                return

        response = chronicle.gemini(
            query=args.query, conversation_id=args.conversation_id
        )

        if args.raw:
            # Output raw API response
            output_formatter(response.get_raw_response(), args.output)
        else:
            # Output formatted text content
            print(response.get_text_content())

            # Print code blocks if any
            code_blocks = response.get_code_blocks()
            if code_blocks:
                print("\nCode blocks:")
                for i, block in enumerate(code_blocks, 1):
                    print(
                        f"\n--- Code Block {i}"
                        + (f" ({block.title})" if block.title else "")
                        + " ---"
                    )
                    print(block.content)

            # Print suggested actions if any
            if response.suggested_actions:
                print("\nSuggested actions:")
                for action in response.suggested_actions:
                    print(f"- {action.display_text}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def setup_help_command(subparsers):
    """Set up the help command parser.

    Args:
        subparsers: Subparsers object to add to
    """
    help_parser = subparsers.add_parser(
        "help", help="Get help with configuration and usage"
    )
    help_parser.add_argument(
        "--topic",
        choices=["config", "customer-id", "project-id"],
        default="config",
        help="Help topic",
    )
    help_parser.set_defaults(func=handle_help_command)


def handle_help_command(args, chronicle=None):
    """Handle help command.

    Args:
        args: Command line arguments
        chronicle: Not used for this command
    """
    # Unused argument
    _ = (chronicle,)

    if args.topic == "config":
        print("Configuration Help:")
        print("------------------")
        print("To use the SecOps CLI with Chronicle, you need to configure:")
        print("  1. Chronicle Customer ID (your Chronicle instance ID)")
        print(
            "  2. GCP Project ID (the Google Cloud project associated with "
            "your Chronicle instance)"
        )
        print("  3. Region (e.g., 'us', 'europe', 'asia-northeast1')")
        print("  4. Optional: Service Account credentials")
        print()
        print("Configuration commands:")
        print(
            "  secops config set --customer-id YOUR_CUSTOMER_ID --project-id "
            "YOUR_PROJECT_ID --region YOUR_REGION"
        )
        print("  secops config view")
        print("  secops config clear")
        print()
        print("For help finding your Customer ID or Project ID, run:")
        print("  secops help --topic customer-id")
        print("  secops help --topic project-id")


def setup_data_table_command(subparsers):
    """Set up the data table command parser."""
    dt_parser = subparsers.add_parser("data-table", help="Manage data tables")
    dt_subparsers = dt_parser.add_subparsers(
        dest="dt_command", help="Data table command"
    )

    # List data tables command
    list_parser = dt_subparsers.add_parser("list", help="List data tables")
    list_parser.add_argument(
        "--order-by",
        "--order_by",
        dest="order_by",
        help="Order by field (only 'createTime asc' is supported)",
    )
    list_parser.set_defaults(func=handle_dt_list_command)

    # Get data table command
    get_parser = dt_subparsers.add_parser("get", help="Get data table details")
    get_parser.add_argument("--name", required=True, help="Data table name")
    get_parser.set_defaults(func=handle_dt_get_command)

    # Create data table command
    create_parser = dt_subparsers.add_parser(
        "create", help="Create a data table"
    )
    create_parser.add_argument("--name", required=True, help="Data table name")
    create_parser.add_argument(
        "--description", required=True, help="Data table description"
    )
    create_parser.add_argument(
        "--header",
        required=True,
        help=(
            "Header definition in JSON format. "
            'Example: \'{"col1":"STRING","col2":"CIDR"}\''
        ),
    )
    create_parser.add_argument(
        "--rows",
        help=(
            'Rows in JSON format. Example: \'[["value1","192.168.1.0/24"],'
            '["value2","10.0.0.0/8"]]\''
        ),
    )
    create_parser.add_argument(
        "--scopes", help="Comma-separated list of scopes"
    )
    create_parser.set_defaults(func=handle_dt_create_command)

    # Delete data table command
    delete_parser = dt_subparsers.add_parser(
        "delete", help="Delete a data table"
    )
    delete_parser.add_argument("--name", required=True, help="Data table name")
    delete_parser.add_argument(
        "--force",
        action="store_true",
        help="Force deletion even if table has rows",
    )
    delete_parser.set_defaults(func=handle_dt_delete_command)

    # List rows command
    list_rows_parser = dt_subparsers.add_parser(
        "list-rows", help="List data table rows"
    )
    list_rows_parser.add_argument(
        "--name", required=True, help="Data table name"
    )
    list_rows_parser.add_argument(
        "--order-by",
        "--order_by",
        dest="order_by",
        help="Order by field (only 'createTime asc' is supported)",
    )
    list_rows_parser.set_defaults(func=handle_dt_list_rows_command)

    # Add rows command
    add_rows_parser = dt_subparsers.add_parser(
        "add-rows", help="Add rows to a data table"
    )
    add_rows_parser.add_argument(
        "--name", required=True, help="Data table name"
    )
    add_rows_parser.add_argument(
        "--rows",
        required=True,
        help=(
            'Rows in JSON format. Example: \'[["value1","192.168.1.0/24"],'
            '["value2","10.0.0.0/8"]]\''
        ),
    )
    add_rows_parser.set_defaults(func=handle_dt_add_rows_command)

    # Delete rows command
    delete_rows_parser = dt_subparsers.add_parser(
        "delete-rows", help="Delete rows from a data table"
    )
    delete_rows_parser.add_argument(
        "--name", required=True, help="Data table name"
    )
    delete_rows_parser.add_argument(
        "--row-ids",
        "--row_ids",
        dest="row_ids",
        required=True,
        help="Comma-separated list of row IDs",
    )
    delete_rows_parser.set_defaults(func=handle_dt_delete_rows_command)


def setup_reference_list_command(subparsers):
    """Set up the reference list command parser."""
    rl_parser = subparsers.add_parser(
        "reference-list", help="Manage reference lists"
    )
    rl_subparsers = rl_parser.add_subparsers(
        dest="rl_command", help="Reference list command"
    )

    # List reference lists command
    list_parser = rl_subparsers.add_parser("list", help="List reference lists")
    list_parser.add_argument(
        "--view", choices=["BASIC", "FULL"], default="BASIC", help="View type"
    )
    list_parser.set_defaults(func=handle_rl_list_command)

    # Get reference list command
    get_parser = rl_subparsers.add_parser(
        "get", help="Get reference list details"
    )
    get_parser.add_argument("--name", required=True, help="Reference list name")
    get_parser.add_argument(
        "--view", choices=["BASIC", "FULL"], default="FULL", help="View type"
    )
    get_parser.set_defaults(func=handle_rl_get_command)

    # Create reference list command
    create_parser = rl_subparsers.add_parser(
        "create", help="Create a reference list"
    )
    create_parser.add_argument(
        "--name", required=True, help="Reference list name"
    )
    create_parser.add_argument(
        "--description", default="", help="Reference list description"
    )
    create_parser.add_argument(
        "--entries", help="Comma-separated list of entries"
    )
    create_parser.add_argument(
        "--syntax-type",
        "--syntax_type",
        dest="syntax_type",
        choices=["STRING", "REGEX", "CIDR"],
        default="STRING",
        help="Syntax type",
    )
    create_parser.add_argument(
        "--entries-file",
        "--entries_file",
        dest="entries_file",
        help="Path to file containing entries (one per line)",
    )
    create_parser.set_defaults(func=handle_rl_create_command)

    # Update reference list command
    update_parser = rl_subparsers.add_parser(
        "update", help="Update a reference list"
    )
    update_parser.add_argument(
        "--name", required=True, help="Reference list name"
    )
    update_parser.add_argument(
        "--description", help="New reference list description"
    )
    update_parser.add_argument(
        "--entries", help="Comma-separated list of entries"
    )
    update_parser.add_argument(
        "--entries-file",
        "--entries_file",
        dest="entries_file",
        help="Path to file containing entries (one per line)",
    )
    update_parser.set_defaults(func=handle_rl_update_command)

    # Note: Reference List deletion is currently not supported by the API


def handle_dt_list_command(args, chronicle):
    """Handle data table list command."""
    try:
        order_by = (
            args.order_by
            if hasattr(args, "order_by") and args.order_by
            else None
        )
        result = chronicle.list_data_tables(order_by=order_by)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_dt_get_command(args, chronicle):
    """Handle data table get command."""
    try:
        result = chronicle.get_data_table(args.name)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_dt_create_command(args, chronicle):
    """Handle data table create command."""
    try:
        # Parse header
        try:
            header_dict = json.loads(args.header)
            # Convert string values to DataTableColumnType enum
            header = {k: DataTableColumnType[v] for k, v in header_dict.items()}
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error parsing header: {e}", file=sys.stderr)
            print(
                "Header should be a JSON object mapping column names to types "
                "(STRING, REGEX, CIDR).",
                file=sys.stderr,
            )
            sys.exit(1)

        # Parse rows if provided
        rows = None
        if args.rows:
            try:
                rows = json.loads(args.rows)
            except json.JSONDecodeError as e:
                print(f"Error parsing rows: {e}", file=sys.stderr)
                print("Rows should be a JSON array of arrays.", file=sys.stderr)
                sys.exit(1)

        # Parse scopes if provided
        scopes = None
        if args.scopes:
            scopes = [s.strip() for s in args.scopes.split(",")]

        result = chronicle.create_data_table(
            name=args.name,
            description=args.description,
            header=header,
            rows=rows,
            scopes=scopes,
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_dt_delete_command(args, chronicle):
    """Handle data table delete command."""
    try:
        result = chronicle.delete_data_table(args.name, force=args.force)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_dt_list_rows_command(args, chronicle):
    """Handle data table list rows command."""
    try:
        order_by = (
            args.order_by
            if hasattr(args, "order_by") and args.order_by
            else None
        )
        result = chronicle.list_data_table_rows(args.name, order_by=order_by)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_dt_add_rows_command(args, chronicle):
    """Handle data table add rows command."""
    try:
        try:
            rows = json.loads(args.rows)
        except json.JSONDecodeError as e:
            print(f"Error parsing rows: {e}", file=sys.stderr)
            print("Rows should be a JSON array of arrays.", file=sys.stderr)
            sys.exit(1)

        result = chronicle.create_data_table_rows(args.name, rows)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_dt_delete_rows_command(args, chronicle):
    """Handle data table delete rows command."""
    try:
        row_ids = [id.strip() for id in args.row_ids.split(",")]
        result = chronicle.delete_data_table_rows(args.name, row_ids)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rl_list_command(args, chronicle):
    """Handle reference list list command."""
    try:
        view = ReferenceListView[args.view]
        result = chronicle.list_reference_lists(view=view)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rl_get_command(args, chronicle):
    """Handle reference list get command."""
    try:
        view = ReferenceListView[args.view]
        result = chronicle.get_reference_list(args.name, view=view)
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rl_create_command(args, chronicle):
    """Handle reference list create command."""
    try:
        # Get entries from file or command line
        entries = []
        if args.entries_file:
            try:
                with open(args.entries_file, "r", encoding="utf-8") as f:
                    entries = [line.strip() for line in f if line.strip()]
            except IOError as e:
                print(f"Error reading entries file: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.entries:
            entries = [e.strip() for e in args.entries.split(",")]

        syntax_type = ReferenceListSyntaxType[args.syntax_type]

        result = chronicle.create_reference_list(
            name=args.name,
            description=args.description,
            entries=entries,
            syntax_type=syntax_type,
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_rl_update_command(args, chronicle):
    """Handle reference list update command."""
    try:
        # Get entries from file or command line
        entries = None
        if args.entries_file:
            try:
                with open(args.entries_file, "r", encoding="utf-8") as f:
                    entries = [line.strip() for line in f if line.strip()]
            except IOError as e:
                print(f"Error reading entries file: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.entries:
            entries = [e.strip() for e in args.entries.split(",")]

        result = chronicle.update_reference_list(
            name=args.name, description=args.description, entries=entries
        )
        output_formatter(result, args.output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Google SecOps CLI")

    # Global arguments
    add_common_args(parser)
    add_chronicle_args(parser)

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(
        dest="command", help="Command to execute"
    )

    # Set up individual command parsers
    setup_search_command(subparsers)
    setup_stats_command(subparsers)
    setup_entity_command(subparsers)
    setup_iocs_command(subparsers)
    setup_log_command(subparsers)
    setup_parser_command(subparsers)
    setup_feed_command(subparsers)
    setup_rule_command(subparsers)
    setup_alert_command(subparsers)
    setup_case_command(subparsers)
    setup_export_command(subparsers)
    setup_gemini_command(subparsers)
    setup_data_table_command(subparsers)  # Add data table command
    setup_reference_list_command(subparsers)  # Add reference list command
    setup_config_command(subparsers)
    setup_help_command(subparsers)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle config commands directly without setting up Chronicle client
    if args.command == "config" or args.command == "help":
        args.func(args)
        return

    # Check if this is a Chronicle-related command that requires configuration
    chronicle_commands = [
        "search",
        "stats",
        "entity",
        "iocs",
        "rule",
        "alert",
        "case",
        "export",
        "gemini",
    ]
    requires_chronicle = any(cmd in args.command for cmd in chronicle_commands)

    if requires_chronicle:
        # Check for required configuration before attempting to
        # create the client
        config = load_config()
        customer_id = args.customer_id or config.get("customer_id")
        project_id = args.project_id or config.get("project_id")

        if not customer_id or not project_id:
            missing = []
            if not customer_id:
                missing.append("customer_id")
            if not project_id:
                missing.append("project_id")

            print(
                f'Error: Missing required configuration: {", ".join(missing)}',
                file=sys.stderr,
            )
            print("\nPlease set up your configuration first:", file=sys.stderr)
            print(
                "  secops config set --customer-id YOUR_CUSTOMER_ID "
                "--project-id YOUR_PROJECT_ID --region YOUR_REGION",
                file=sys.stderr,
            )
            print(
                "\nOr provide them directly on the command line:",
                file=sys.stderr,
            )
            print(
                "  secops --customer-id YOUR_CUSTOMER_ID --project-id "
                f"YOUR_PROJECT_ID --region YOUR_REGION {args.command}",
                file=sys.stderr,
            )
            print("\nNeed help finding these values?", file=sys.stderr)
            print("  secops help --topic customer-id", file=sys.stderr)
            print("  secops help --topic project-id", file=sys.stderr)
            print("\nFor general configuration help:", file=sys.stderr)
            print("  secops help --topic config", file=sys.stderr)
            sys.exit(1)

    # Set up client
    client, chronicle = setup_client(args)  # pylint: disable=unused-variable

    # Execute command
    if hasattr(args, "func"):
        if not requires_chronicle or chronicle is not None:
            args.func(args, chronicle)
        else:
            print(
                "Error: Chronicle client required for this command",
                file=sys.stderr,
            )
            print("\nFor help with configuration:", file=sys.stderr)
            print("  secops help --topic config", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
