# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Chronicle API client."""
import ipaddress
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterator, List, Literal, Optional, Union

from google.auth.transport import requests as google_auth_requests

from secops import auth as secops_auth
from secops.chronicle.alert import get_alerts as _get_alerts
from secops.chronicle.case import get_cases_from_list
from secops.chronicle.data_export import (
    cancel_data_export as _cancel_data_export,
)
from secops.chronicle.data_export import (
    create_data_export as _create_data_export,
)
from secops.chronicle.data_export import (
    fetch_available_log_types as _fetch_available_log_types,
)
from secops.chronicle.data_export import get_data_export as _get_data_export
from secops.chronicle.data_table import DataTableColumnType
from secops.chronicle.data_table import create_data_table as _create_data_table
from secops.chronicle.data_table import (
    create_data_table_rows as _create_data_table_rows,
)
from secops.chronicle.data_table import delete_data_table as _delete_data_table
from secops.chronicle.data_table import (
    delete_data_table_rows as _delete_data_table_rows,
)
from secops.chronicle.data_table import get_data_table as _get_data_table
from secops.chronicle.data_table import (
    list_data_table_rows as _list_data_table_rows,
)
from secops.chronicle.data_table import list_data_tables as _list_data_tables
from secops.chronicle.entity import _detect_value_type_for_query
from secops.chronicle.entity import summarize_entity as _summarize_entity
from secops.chronicle.gemini import GeminiResponse
from secops.chronicle.gemini import opt_in_to_gemini as _opt_in_to_gemini
from secops.chronicle.gemini import query_gemini as _query_gemini
from secops.chronicle.ioc import list_iocs as _list_iocs
from secops.chronicle.log_ingest import (
    get_or_create_forwarder as _get_or_create_forwarder,
)
from secops.chronicle.log_ingest import ingest_log as _ingest_log
from secops.chronicle.log_ingest import ingest_udm as _ingest_udm
from secops.chronicle.log_types import LogType
from secops.chronicle.log_types import get_all_log_types as _get_all_log_types
from secops.chronicle.log_types import (
    get_log_type_description as _get_log_type_description,
)
from secops.chronicle.log_types import is_valid_log_type as _is_valid_log_type
from secops.chronicle.log_types import search_log_types as _search_log_types
from secops.chronicle.models import CaseList, EntitySummary
from secops.chronicle.nl_search import nl_search as _nl_search
from secops.chronicle.nl_search import translate_nl_to_udm
from secops.chronicle.reference_list import (
    ReferenceListSyntaxType,
    ReferenceListView,
)
from secops.chronicle.reference_list import (
    create_reference_list as _create_reference_list,
)
from secops.chronicle.reference_list import (
    get_reference_list as _get_reference_list,
)
from secops.chronicle.reference_list import (
    list_reference_lists as _list_reference_lists,
)
from secops.chronicle.reference_list import (
    update_reference_list as _update_reference_list,
)

from secops.chronicle.feeds import (
    list_feeds as _list_feeds,
    get_feed as _get_feed,
    create_feed as _create_feed,
    update_feed as _update_feed,
    delete_feed as _delete_feed,
    enable_feed as _enable_feed,
    disable_feed as _disable_feed,
    generate_secret as _generate_secret,
    CreateFeedModel,
    UpdateFeedModel,
)

# Import rule functions
from secops.chronicle.rule import create_rule as _create_rule
from secops.chronicle.rule import delete_rule as _delete_rule
from secops.chronicle.rule import enable_rule as _enable_rule
from secops.chronicle.rule import get_rule as _get_rule
from secops.chronicle.rule import list_rules as _list_rules
from secops.chronicle.rule import run_rule_test
from secops.chronicle.rule import search_rules as _search_rules
from secops.chronicle.rule import update_rule as _update_rule
from secops.chronicle.rule_alert import (
    bulk_update_alerts as _bulk_update_alerts,
)
from secops.chronicle.rule_alert import get_alert as _get_alert
from secops.chronicle.rule_alert import (
    search_rule_alerts as _search_rule_alerts,
)
from secops.chronicle.rule_alert import update_alert as _update_alert
from secops.chronicle.rule_detection import list_detections as _list_detections
from secops.chronicle.rule_detection import list_errors as _list_errors
from secops.chronicle.rule_retrohunt import (
    create_retrohunt as _create_retrohunt,
)
from secops.chronicle.rule_retrohunt import get_retrohunt as _get_retrohunt
from secops.chronicle.rule_set import (
    batch_update_curated_rule_set_deployments as _batch_update_curated_rule_set_deployments,  # pylint: disable=line-too-long
)
from secops.chronicle.search import search_udm as _search_udm
from secops.chronicle.stats import get_stats as _get_stats

# Import functions from the new modules
from secops.chronicle.udm_search import (
    fetch_udm_search_csv as _fetch_udm_search_csv,
)
from secops.chronicle.validate import validate_query as _validate_query

from .parser import activate_parser as _activate_parser
from .parser import (
    activate_release_candidate_parser as _activate_release_candidate_parser,
)
from .parser import copy_parser as _copy_parser
from .parser import create_parser as _create_parser
from .parser import deactivate_parser as _deactivate_parser
from .parser import delete_parser as _delete_parser
from .parser import get_parser as _get_parser
from .parser import list_parsers as _list_parsers
from .parser import run_parser as _run_parser
from .rule_validation import validate_rule as _validate_rule


class ValueType(Enum):
    """Chronicle API value types."""

    ASSET_IP_ADDRESS = "ASSET_IP_ADDRESS"
    MAC = "MAC"
    HOSTNAME = "HOSTNAME"
    DOMAIN_NAME = "DOMAIN_NAME"
    HASH_MD5 = "HASH_MD5"
    HASH_SHA256 = "HASH_SHA256"
    HASH_SHA1 = "HASH_SHA1"
    EMAIL = "EMAIL"
    USERNAME = "USERNAME"


def _detect_value_type(value: str) -> tuple[Optional[str], Optional[str]]:
    """Detect value type from a string.

    Args:
        value: The value to detect type for

    Returns:
        Tuple of (field_path, value_type) where one or both may be None
    """
    # Try to detect IP address
    try:
        ipaddress.ip_address(value)
        return "principal.ip", None
    except ValueError:
        pass

    # Try to detect MD5 hash
    if re.match(r"^[a-fA-F0-9]{32}$", value):
        return "target.file.md5", None

    # Try to detect SHA-1 hash
    if re.match(r"^[a-fA-F0-9]{40}$", value):
        return "target.file.sha1", None

    # Try to detect SHA-256 hash
    if re.match(r"^[a-fA-F0-9]{64}$", value):
        return "target.file.sha256", None

    # Try to detect domain name
    if re.match(
        r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9](?:\.[a-zA-Z]{2,})+$", value
    ):
        return None, "DOMAIN_NAME"

    # Try to detect email address
    if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", value):
        return None, "EMAIL"

    # Try to detect MAC address
    if re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", value):
        return None, "MAC"

    # Try to detect hostname (simple rule)
    if re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$", value):
        return None, "HOSTNAME"

    # If no match found
    return None, None


class ChronicleClient:
    """Client for the Chronicle API."""

    def __init__(
        self,
        project_id: str,
        customer_id: str,
        region: str = "us",
        auth: Optional[Any] = None,
        session: Optional[Any] = None,
        extra_scopes: Optional[List[str]] = None,
        credentials: Optional[Any] = None,
    ):
        """Initialize ChronicleClient.

        Args:
            project_id: Google Cloud project ID
            customer_id: Chronicle customer ID
            region: Chronicle region, typically "us" or "eu"
            auth: Authentication object
            session: Custom session object
            extra_scopes: Additional OAuth scopes
            credentials: Credentials object
        """
        self.project_id = project_id
        self.customer_id = customer_id
        self.region = region
        self._default_forwarder_display_name: str = "Wrapper-SDK-Forwarder"
        self._cached_default_forwarder_id: Optional[str] = None

        # Format the instance ID to match the expected format
        if region in ["dev", "staging"]:
            # For dev and staging environments,
            # use a different instance ID format
            self.instance_id = (
                f"projects/{project_id}/locations/us/instances/{customer_id}"
            )
            # Set up the base URL for dev/staging
            if region == "dev":
                self.base_url = (
                    "https://dev-chronicle.sandbox.googleapis.com/v1alpha"
                )
            else:  # staging
                self.base_url = (
                    "https://staging-chronicle.sandbox.googleapis.com/v1alpha"
                )
        else:
            # Standard production regions use the normal format
            self.instance_id = (
                f"projects/{project_id}/locations/{region}/"
                f"instances/{customer_id}"
            )
            # Set up the base URL
            self.base_url = (
                f"https://{self.region}-chronicle.googleapis.com/v1alpha"
            )

        # Create a session with authentication
        if session:
            self._session = session
        else:
            if auth is None:
                auth = secops_auth.SecOpsAuth(
                    scopes=[
                        "https://www.googleapis.com/auth/cloud-platform",
                        "https://www.googleapis.com/auth/chronicle-backstory",
                    ]
                    + (extra_scopes or []),
                    credentials=credentials,
                )

            self._session = auth.session

        # Ensure custom user agent is set
        if hasattr(self._session, "headers"):
            self._session.headers["User-Agent"] = "secops-wrapper-sdk"

    @property
    def session(self) -> google_auth_requests.AuthorizedSession:
        """Get an authenticated session.

        Returns:
            Authorized session for API requests
        """
        return self._session

    def fetch_udm_search_csv(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        fields: list[str],
        case_insensitive: bool = True,
    ) -> str:
        """Fetch UDM search results in CSV format.

        Args:
            query: Chronicle search query
            start_time: Search start time
            end_time: Search end time
            fields: List of fields to include in results
            case_insensitive: Whether to perform case-insensitive search

        Returns:
            CSV formatted string of results

        Raises:
            APIError: If the API request fails
        """
        return _fetch_udm_search_csv(
            self, query, start_time, end_time, fields, case_insensitive
        )

    def validate_query(self, query: str) -> Dict[str, Any]:
        """Validate a Chronicle search query.

        Args:
            query: Chronicle search query to validate

        Returns:
            Dictionary with validation results

        Raises:
            APIError: If the API request fails
        """
        return _validate_query(self, query)

    def get_stats(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        max_values: int = 60,
        timeout: int = 120,
        max_events: int = 10000,
        case_insensitive: bool = True,
        max_attempts: int = 30,
    ) -> Dict[str, Any]:
        """Get statistics from a Chronicle search query.

        Args:
            query: Chronicle search query in stats format
            start_time: Search start time
            end_time: Search end time
            max_values: Maximum number of values to return per field
            timeout: Timeout in seconds for API request (default: 120)
            max_events: Maximum number of events to process
            case_insensitive: Whether to perform case-insensitive search
            max_attempts: Maximum number of polling attempts (deprecated)

        Returns:
            Dictionary with search statistics containing:
            - columns: List of column names
            - rows: List of dictionaries with row data
            - total_rows: Total number of rows

        Raises:
            APIError: If the API request fails
        """
        return _get_stats(
            self,
            query,
            start_time,
            end_time,
            max_values,
            timeout,
            max_events,
            case_insensitive,
            max_attempts,
        )

    def _process_stats_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Process stats search results.

        Args:
            results: Stats search results from API

        Returns:
            Processed statistics
        """
        processed_results = {"total_rows": 0, "columns": [], "rows": []}

        # Return early if no stats results
        if "stats" not in results or "results" not in results["stats"]:
            return processed_results

        # Extract columns
        columns = []
        column_data = {}

        for col_data in results["stats"]["results"]:
            col_name = col_data.get("column", "")
            columns.append(col_name)

            # Process values for this column
            values = []
            for val_data in col_data.get("values", []):
                if "value" in val_data:
                    val = val_data["value"]
                    if "int64Val" in val:
                        values.append(int(val["int64Val"]))
                    elif "doubleVal" in val:
                        values.append(float(val["doubleVal"]))
                    elif "stringVal" in val:
                        values.append(val["stringVal"])
                    else:
                        values.append(None)
                else:
                    values.append(None)

            column_data[col_name] = values

        # Build result rows
        rows = []
        if columns and all(col in column_data for col in columns):
            max_rows = max(len(column_data[col]) for col in columns)
            processed_results["total_rows"] = max_rows

            for i in range(max_rows):
                row = {}
                for col in columns:
                    col_values = column_data[col]
                    row[col] = col_values[i] if i < len(col_values) else None
                rows.append(row)

        processed_results["columns"] = columns
        processed_results["rows"] = rows

        return processed_results

    def search_udm(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        max_events: int = 10000,
        case_insensitive: bool = True,
        max_attempts: int = 30,
        timeout: int = 30,
        debug: bool = False,
    ) -> Dict[str, Any]:
        """Search UDM events in Chronicle.

        Args:
            query: Chronicle search query
            start_time: Search start time
            end_time: Search end time
            max_events: Maximum events to return
            case_insensitive: Whether to perform case-insensitive search
            max_attempts: Maximum number of polling attempts (default: 30)
            timeout: Timeout in seconds for each API request (default: 30)
            debug: Print debug information during execution

        Returns:
            Dictionary with search results containing:
            - events: List of UDM events with 'name' and 'udm' fields
            - total_events: Number of events returned
            - more_data_available: Boolean indicating
                if more results are available

        Raises:
            APIError: If the API request fails
        """
        return _search_udm(
            self,
            query,
            start_time,
            end_time,
            max_events,
            case_insensitive,
            max_attempts,
            timeout,
            debug,
        )

    def summarize_entity(
        self,
        value: str,
        start_time: datetime,
        end_time: datetime,
        preferred_entity_type: Optional[str] = None,
        include_all_udm_types: bool = True,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> EntitySummary:
        """
        Get comprehensive summary information about an entity
        (IP, domain, file hash, etc.).

        This function mimics the Chronicle UI behavior:
        1. It first calls `summarizeEntitiesFromQuery` using a query
            derived from the value.
        2. It identifies a 'primary' entity from the results
            (preferring ASSET for IPs/MACs/Hostnames, FILE for hashes,
            DOMAIN_NAME for domains, USER for emails).
        3. If a primary entity is found, it makes subsequent calls to
            `summarizeEntity` using the primary entity's ID to fetch details
            like alerts, timeline, and prevalence.
        4. It combines all information into a single EntitySummary object.

        Args:
            value: The entity value to search for
                (e.g., "8.8.8.8", "google.com", hash).
            start_time: Start time for the summary data range.
            end_time: End time for the summary data range.
            preferred_entity_type: Optionally hint the preferred type
                                   ("ASSET", "FILE", "DOMAIN_NAME", "USER").
                                   If None, the function attempts to autodetect.
            include_all_udm_types: Whether to include all UDM event types for
                first/last seen times.
            page_size: Maximum number of results per page
                (primarily for alerts).
            page_token: Token for pagination (primarily for alerts).

        Returns:
            An EntitySummary object containing the combined results.

        Raises:
            APIError: If any API request fails or returns unexpected data.
            ValueError: If the input value cannot be mapped to a query.
        """
        return _summarize_entity(
            client=self,
            value=value,
            start_time=start_time,
            end_time=end_time,
            preferred_entity_type=preferred_entity_type,
            include_all_udm_types=include_all_udm_types,
            page_size=page_size,
            page_token=page_token,
        )

    def list_iocs(
        self,
        start_time: datetime,
        end_time: datetime,
        max_matches: int = 1000,
        add_mandiant_attributes: bool = True,
        prioritized_only: bool = False,
    ) -> dict:
        """List IoCs from Chronicle.

        Args:
            start_time: Start time for IoC search
            end_time: End time for IoC search
            max_matches: Maximum number of matches to return
            add_mandiant_attributes: Whether to add Mandiant attributes
            prioritized_only: Whether to only include prioritized IoCs

        Returns:
            Dictionary with IoC matches

        Raises:
            APIError: If the API request fails
        """
        return _list_iocs(
            self,
            start_time,
            end_time,
            max_matches,
            add_mandiant_attributes,
            prioritized_only,
        )

    def get_cases(self, case_ids: list[str]) -> CaseList:
        """Get case information for the specified case IDs.

        Uses the legacy:legacyBatchGetCases endpoint to retrieve multiple cases
        in a single API request.

        Args:
            case_ids: List of case IDs to retrieve (maximum 1000)

        Returns:
            A CaseList object containing the requested cases

        Raises:
            APIError: If the API request fails
            ValueError: If more than 1000 case IDs are provided
        """
        return get_cases_from_list(self, case_ids)

    def get_alerts(
        self,
        start_time: datetime,
        end_time: datetime,
        snapshot_query: str = 'feedback_summary.status != "CLOSED"',
        baseline_query: Optional[str] = None,
        max_alerts: int = 1000,
        enable_cache: bool = True,
        max_attempts: int = 30,
        poll_interval: float = 1.0,
    ) -> dict:
        """Get alerts from Chronicle.

        Args:
            start_time: Start time for alert search
            end_time: End time for alert search
            snapshot_query: Query to filter alerts
            baseline_query: Baseline query to compare against
            max_alerts: Maximum number of alerts to return
            enable_cache: Whether to use cached results
            max_attempts: Maximum number of attempts to poll for results
            poll_interval: Interval between polling attempts in seconds

        Returns:
            Dictionary with alert data

        Raises:
            APIError: If the API request fails or times out
        """
        return _get_alerts(
            self,
            start_time,
            end_time,
            snapshot_query,
            baseline_query,
            max_alerts,
            enable_cache,
            max_attempts,
            poll_interval,
        )

    def _process_alerts_response(self, response) -> list:
        """Process alerts response.

        Args:
            response: Response data from API

        Returns:
            Processed response
        """
        # Simply return the response as it should already be processed
        return response

    def _merge_alert_updates(self, target: dict, updates: list) -> None:
        """Merge alert updates into the target dictionary.

        Args:
            target: Target dictionary to update
            updates: List of updates to apply
        """
        if "alerts" not in target or "alerts" not in target["alerts"]:
            return

        alerts = target["alerts"]["alerts"]

        # Create a map of alerts by ID for faster lookups
        alert_map = {alert["id"]: alert for alert in alerts}

        # Apply updates
        for update in updates:
            if "id" in update and update["id"] in alert_map:
                target_alert = alert_map[update["id"]]

                # Update each field
                for field, value in update.items():
                    if field != "id":
                        if (
                            isinstance(value, dict)
                            and field in target_alert
                            and isinstance(target_alert[field], dict)
                        ):
                            # Merge nested dictionaries
                            target_alert[field].update(value)
                        else:
                            # Replace value
                            target_alert[field] = value

    def _fix_json_formatting(self, json_str: str) -> str:
        """Fix common JSON formatting issues.

        Args:
            json_str: JSON string to fix

        Returns:
            Fixed JSON string
        """
        # Fix trailing commas in objects
        json_str = re.sub(r",\s*}", "}", json_str)
        # Fix trailing commas in arrays
        json_str = re.sub(r",\s*]", "]", json_str)

        return json_str

    # pylint: disable=function-redefined
    def _detect_value_type(
        self, value: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Instance method version of _detect_value_type for
        backward compatibility.

        Args:
            value: The value to detect type for

        Returns:
            Tuple of (field_path, value_type) where one or both may be None
        """
        return _detect_value_type(value)

    def _detect_value_type(self, value, value_type=None):
        """Detect value type for entity values.

        This is a legacy method maintained for backward compatibility.
        It calls the standalone detect_value_type function.

        Args:
            value: Value to detect type for
            value_type: Optional explicit value type

        Returns:
            Tuple of (field_path, value_type)
        """
        _ = (value_type,)
        return _detect_value_type_for_query(value)

    # pylint: enable=function-redefined

    # Rule Management methods

    def create_rule(self, rule_text: str) -> Dict[str, Any]:
        """Creates a new detection rule to find matches in logs.

        Args:
            rule_text: Content of the new detection rule, used to evaluate logs.

        Returns:
            Dictionary containing the created rule information

        Raises:
            APIError: If the API request fails
        """
        return _create_rule(self, rule_text)

    def get_rule(self, rule_id: str) -> Dict[str, Any]:
        """Get a rule by ID.

        Args:
            rule_id: Unique ID of the detection rule to retrieve ("ru_<UUID>" or
              "ru_<UUID>@v_<seconds>_<nanoseconds>"). If a version suffix isn't
              specified we use the rule's latest version.

        Returns:
            Dictionary containing rule information

        Raises:
            APIError: If the API request fails
        """
        return _get_rule(self, rule_id)

    def list_feeds(self) -> Dict[str, Any]:
        return _list_feeds(self)

    def get_feed(self, feed_id: str) -> Dict[str, Any]:
        return _get_feed(self, feed_id)

    def create_feed(
        self, display_name: str, details: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        feed_config = CreateFeedModel(
            display_name=display_name, details=details
        )
        return _create_feed(self, feed_config)

    def update_feed(
        self,
        feed_id: str,
        display_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        feed_config = UpdateFeedModel(
            display_name=display_name, details=details
        )
        return _update_feed(self, feed_id, feed_config)

    def enable_feed(self, feed_id: str) -> Dict[str, Any]:
        return _enable_feed(self, feed_id)

    def disable_feed(self, feed_id: str) -> Dict[str, Any]:
        return _disable_feed(self, feed_id)

    def generate_secret(self, feed_id: str) -> Dict[str, Any]:
        return _generate_secret(self, feed_id)

    def delete_feed(self, feed_id: str) -> Dict[str, Any]:
        return _delete_feed(self, feed_id)

    def list_rules(self) -> Dict[str, Any]:
        """Gets a list of rules.

        Returns:
            Dictionary containing information about rules

        Raises:
            APIError: If the API request fails
        """
        return _list_rules(self)

    def update_rule(self, rule_id: str, rule_text: str) -> Dict[str, Any]:
        """Updates a rule.

        Args:
            rule_id: Unique ID of the detection rule to update ("ru_<UUID>")
            rule_text: Updated content of the detection rule

        Returns:
            Dictionary containing the updated rule information

        Raises:
            APIError: If the API request fails
        """
        return _update_rule(self, rule_id, rule_text)

    def delete_rule(self, rule_id: str, force: bool = False) -> Dict[str, Any]:
        """Deletes a rule.

        Args:
            rule_id: Unique ID of the detection rule to delete ("ru_<UUID>")
            force: If True, deletes the rule even if it has
            associated retrohunts

        Returns:
            Empty dictionary or deletion confirmation

        Raises:
            APIError: If the API request fails
        """
        return _delete_rule(self, rule_id, force)

    def enable_rule(self, rule_id: str, enabled: bool = True) -> Dict[str, Any]:
        """Enables or disables a rule.

        Args:
            rule_id: Unique ID of the detection rule to enable/disable
                ("ru_<UUID>")
            enabled: Whether to enable (True) or disable (False) the rule

        Returns:
            Dictionary containing rule deployment information

        Raises:
            APIError: If the API request fails
        """
        return _enable_rule(self, rule_id, enabled)

    def search_rules(self, query: str) -> Dict[str, Any]:
        """Search for rules.

        Args:
            query: Search query string that supports regex

        Returns:
            Dictionary containing search results

        Raises:
            APIError: If the API request fails
        """
        return _search_rules(self, query)

    def run_rule_test(
        self,
        rule_text: str,
        start_time: datetime,
        end_time: datetime,
        max_results: int = 100,
        timeout: int = 300,
    ) -> Iterator[Dict[str, Any]]:
        """Tests a rule against historical data and returns matches.

        This function connects to the legacy:legacyRunTestRule streaming
        API endpoint and processes the response which contains progress updates
        and detection results.

        Args:
            rule_text: Content of the detection rule to test
            start_time: Start time for the test range
            end_time: End time for the test range
            max_results: Maximum number of results to return
                (default 100, max 10000)
            timeout: Request timeout in seconds (default 300)

        Yields:
            Dictionaries containing detection results, progress updates
            or error information, depending on the response type.

        Raises:
            APIError: If the API request fails
            SecOpsError: If the input parameters are invalid
            ValueError: If max_results is outside valid range
        """
        return run_rule_test(
            self, rule_text, start_time, end_time, max_results, timeout
        )

    # Rule Alert methods

    def get_alert(
        self, alert_id: str, include_detections: bool = False
    ) -> Dict[str, Any]:
        """Gets an alert by ID.

        Args:
            alert_id: ID of the alert to retrieve
            include_detections: Whether to include detection details in
                the response

        Returns:
            Dictionary containing alert information

        Raises:
            APIError: If the API request fails
        """
        return _get_alert(self, alert_id, include_detections)

    def update_alert(
        self,
        alert_id: str,
        confidence_score: Optional[int] = None,
        reason: Optional[str] = None,
        reputation: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        verdict: Optional[str] = None,
        risk_score: Optional[int] = None,
        disregarded: Optional[bool] = None,
        severity: Optional[int] = None,
        comment: Optional[Union[str, Literal[""]]] = None,
        root_cause: Optional[Union[str, Literal[""]]] = None,
    ) -> Dict[str, Any]:
        """Updates an alert's properties.

        Args:
            alert_id: ID of the alert to update
            confidence_score: Confidence score [0-100] of the alert
            reason: Reason for closing an alert. Valid values:
                - "REASON_UNSPECIFIED"
                - "REASON_NOT_MALICIOUS"
                - "REASON_MALICIOUS"
                - "REASON_MAINTENANCE"
            reputation: Categorization of usefulness. Valid values:
                - "REPUTATION_UNSPECIFIED"
                - "USEFUL"
                - "NOT_USEFUL"
            priority: Alert priority. Valid values:
                - "PRIORITY_UNSPECIFIED"
                - "PRIORITY_INFO"
                - "PRIORITY_LOW"
                - "PRIORITY_MEDIUM"
                - "PRIORITY_HIGH"
                - "PRIORITY_CRITICAL"
            status: Alert status. Valid values:
                - "STATUS_UNSPECIFIED"
                - "NEW"
                - "REVIEWED"
                - "CLOSED"
                - "OPEN"
            verdict: Verdict on the alert. Valid values:
                - "VERDICT_UNSPECIFIED"
                - "TRUE_POSITIVE"
                - "FALSE_POSITIVE"
            risk_score: Risk score [0-100] of the alert
            disregarded: Whether the alert should be disregarded
            severity: Severity score [0-100] of the alert
            comment: Analyst comment (empty string is valid to clear)
            root_cause: Alert root cause (empty string is valid to clear)

        Returns:
            Dictionary containing updated alert information

        Raises:
            APIError: If the API request fails
            ValueError: If invalid values are provided
        """
        return _update_alert(
            self,
            alert_id,
            confidence_score,
            reason,
            reputation,
            priority,
            status,
            verdict,
            risk_score,
            disregarded,
            severity,
            comment,
            root_cause,
        )

    def bulk_update_alerts(
        self,
        alert_ids: List[str],
        confidence_score: Optional[int] = None,
        reason: Optional[str] = None,
        reputation: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        verdict: Optional[str] = None,
        risk_score: Optional[int] = None,
        disregarded: Optional[bool] = None,
        severity: Optional[int] = None,
        comment: Optional[Union[str, Literal[""]]] = None,
        root_cause: Optional[Union[str, Literal[""]]] = None,
    ) -> List[Dict[str, Any]]:
        """Updates multiple alerts with the same properties.

        This is a helper function that iterates through the list of alert IDs
        and applies the same updates to each alert.

        Args:
            alert_ids: List of alert IDs to update
            confidence_score: Confidence score [0-100] of the alert
            reason: Reason for closing an alert
            reputation: Categorization of usefulness
            priority: Alert priority
            status: Alert status
            verdict: Verdict on the alert
            risk_score: Risk score [0-100] of the alert
            disregarded: Whether the alert should be disregarded
            severity: Severity score [0-100] of the alert
            comment: Analyst comment (empty string is valid to clear)
            root_cause: Alert root cause (empty string is valid to clear)

        Returns:
            List of dictionaries containing updated alert information

        Raises:
            APIError: If any API request fails
            ValueError: If invalid values are provided
        """
        return _bulk_update_alerts(
            self,
            alert_ids,
            confidence_score,
            reason,
            reputation,
            priority,
            status,
            verdict,
            risk_score,
            disregarded,
            severity,
            comment,
            root_cause,
        )

    def search_rule_alerts(
        self,
        start_time: datetime,
        end_time: datetime,
        rule_status: Optional[str] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Search for alerts generated by rules.

        Args:
            start_time: Start time for the search (inclusive)
            end_time: End time for the search (exclusive)
            rule_status: Filter by rule status (deprecated - not currently
                supported by the API)
            page_size: Maximum number of alerts to return

        Returns:
            Dictionary containing alert search results

        Raises:
            APIError: If the API request fails
        """

        return _search_rule_alerts(
            self, start_time, end_time, rule_status, page_size
        )

    # Rule Detection methods

    def list_detections(
        self,
        rule_id: str,
        alert_state: Optional[str] = None,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List detections for a rule.

        Args:
            rule_id: Unique ID of the rule to list detections for. Options are:
                - {rule_id} (latest version)
                - {rule_id}@v_<seconds>_<nanoseconds> (specific version)
                - {rule_id}@- (all versions)
            alert_state: If provided, filter by alert state. Valid values are:
                - "UNSPECIFIED"
                - "NOT_ALERTING"
                - "ALERTING"
            page_size: If provided, maximum number of detections to return
            page_token: If provided, continuation token for pagination

        Returns:
            Dictionary containing detection information

        Raises:
            APIError: If the API request fails
            ValueError: If an invalid alert_state is provided
        """
        return _list_detections(
            self, rule_id, alert_state, page_size, page_token
        )

    def list_errors(self, rule_id: str) -> Dict[str, Any]:
        """List execution errors for a rule.

        Args:
            rule_id: Unique ID of the rule to list errors for. Options are:
                - {rule_id} (latest version)
                - {rule_id}@v_<seconds>_<nanoseconds> (specific version)
                - {rule_id}@- (all versions)

        Returns:
            Dictionary containing rule execution errors

        Raises:
            APIError: If the API request fails
        """
        return _list_errors(self, rule_id)

    # Rule Retrohunt methods

    def create_retrohunt(
        self, rule_id: str, start_time: datetime, end_time: datetime
    ) -> Dict[str, Any]:
        """Creates a retrohunt for a rule.

        A retrohunt applies a rule to historical data within
        the specified time range.

        Args:
            rule_id: Unique ID of the rule to run retrohunt for ("ru_<UUID>")
            start_time: Start time for retrohunt analysis
            end_time: End time for retrohunt analysis

        Returns:
            Dictionary containing operation information for the retrohunt

        Raises:
            APIError: If the API request fails
        """
        return _create_retrohunt(self, rule_id, start_time, end_time)

    def get_retrohunt(self, rule_id: str, operation_id: str) -> Dict[str, Any]:
        """Get retrohunt status and results.

        Args:
            rule_id: Unique ID of the rule the retrohunt is for ("ru_<UUID>" or
              "ru_<UUID>@v_<seconds>_<nanoseconds>")
            operation_id: Operation ID of the retrohunt

        Returns:
            Dictionary containing retrohunt information

        Raises:
            APIError: If the API request fails
        """
        return _get_retrohunt(self, rule_id, operation_id)

    # Parser Management methods

    def activate_parser(
        self, log_type: str, id: str  # pylint: disable=redefined-builtin
    ) -> Dict[str, Any]:
        """Activate a custom parser.

        Args:
            log_type: Log type of the parser
            id: Parser ID

        Returns:
            Empty JSON object

        Raises:
            APIError: If the API request fails
        """
        return _activate_parser(self, log_type=log_type, id=id)

    def activate_release_candidate_parser(
        self, log_type: str, id: str  # pylint: disable=redefined-builtin
    ) -> Dict[str, Any]:
        """
        Activate the release candidate parser making it live for that customer.

        Args:
            log_type: Log type of the parser
            id: Parser ID

        Returns:
            Empty JSON object

        Raises:
            APIError: If the API request fails
        """
        return _activate_release_candidate_parser(
            self, log_type=log_type, id=id
        )

    def copy_parser(
        self, log_type: str, id: str  # pylint: disable=redefined-builtin
    ) -> Dict[str, Any]:
        """Makes a copy of a prebuilt parser.

        Args:
            log_type: Log type of the parser
            id: Parser ID

        Returns:
            Dictionary containing the newly copied parser

        Raises:
            APIError: If the API request fails
        """
        return _copy_parser(client=self, log_type=log_type, id=id)

    def create_parser(
        self, log_type: str, parser_code: str, validated_on_empty_logs: bool
    ) -> Dict[str, Any]:
        """Creates a new parser.

        Args:
            log_type: Log type of the parser
            parser_code: Content of the new parser, used to evaluate logs
            validated_on_empty_logs: Whether the parser is validated
                on empty logs

        Returns:
            Dictionary containing the created parser information

        Raises:
            APIError: If the API request fails
        """
        return _create_parser(
            self,
            log_type=log_type,
            parser_code=parser_code,
            validated_on_empty_logs=validated_on_empty_logs,
        )

    def deactivate_parser(
        self, log_type: str, id: str  # pylint: disable=redefined-builtin
    ) -> Dict[str, Any]:
        """Deactivate a custom parser.

        Args:
            log_type: Log type of the parser
            id: Parser ID

        Returns:
            Empty JSON object

        Raises:
            APIError: If the API request fails
        """
        return _deactivate_parser(client=self, log_type=log_type, id=id)

    def delete_parser(
        self,
        log_type: str,
        id: str,  # pylint: disable=redefined-builtin
        force: bool = False,
    ) -> Dict[str, Any]:
        """Delete a parser.

        Args:
            log_type: Log type of the parser
            id: Parser ID
            force: Flag to forcibly delete an ACTIVE parser

        Returns:
            Empty JSON object

        Raises:
            APIError: If the API request fails
        """
        return _delete_parser(
            client=self, log_type=log_type, id=id, force=force
        )

    def get_parser(
        self, log_type: str, id: str  # pylint: disable=redefined-builtin
    ) -> Dict[str, Any]:
        """Get a parser by ID.

        Args:
            log_type: Log type of the parser
            id: Parser ID

        Returns:
            Dictionary containing the parser information

        Raises:
            APIError: If the API request fails
        """
        return _get_parser(self, log_type=log_type, id=id)

    def list_parsers(
        self,
        log_type: str = "-",
        page_size: int = 100,
        page_token: str = None,
        filter: str = None,  # pylint: disable=redefined-builtin
    ) -> List[Any]:
        """List parsers.

        Args:
            log_type: Log type to filter by
            page_size: The maximum number of parsers to return
            page_token: A page token, received from a previous ListParsers call
            filter: Optional filter expression

        Returns:
            List of parser dictionaries

        Raises:
            APIError: If the API request fails
        """
        return _list_parsers(
            self,
            log_type=log_type,
            page_size=page_size,
            page_token=page_token,
            filter=filter,
        )

    def run_parser(
        self,
        log_type: str,
        parser_code: str,
        parser_extension_code: str,
        logs: list,
        statedump_allowed: bool = False,
    ):
        """Run parser against sample logs.

        Args:
            client: ChronicleClient instance
            log_type: Log type of the parser
            parser_code: Content of the new parser, used to evaluate logs.
            parser_extension_code: Content of the parser extension
            logs: list of logs to test parser against
            statedump_allowed: Statedump filter is enabled or not for a config

        Returns:
            Dictionary containing the parser result

        Raises:
            APIError: If the API request fails
        """
        return _run_parser(
            self,
            log_type=log_type,
            parser_code=parser_code,
            parser_extension_code=parser_extension_code,
            logs=logs,
            statedump_allowed=statedump_allowed,
        )

    # Rule Set methods

    def batch_update_curated_rule_set_deployments(
        self, deployments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Batch update curated rule set deployments.

        Args:
            deployments: List of deployment configurations where each
                item contains:
                - category_id: UUID of the category
                - rule_set_id: UUID of the rule set
                - precision: Precision level (e.g., "broad", "precise")
                - enabled: Whether the rule set should be enabled
                - alerting: Whether alerting should be enabled for the rule set

        Returns:
            Dictionary containing information about the modified deployments

        Raises:
            APIError: If the API request fails
            ValueError: If required fields are missing from the deployments
        """
        return _batch_update_curated_rule_set_deployments(self, deployments)

    def validate_rule(self, rule_text: str):
        """Validates a YARA-L2 rule against the Chronicle API.

        Args:
            rule_text: Content of the rule to validate

        Returns:
            ValidationResult containing:
                - success: Whether the rule is valid
                - message: Error message if validation failed,
                    None if successful
                - position: Dictionary containing position information for
                    errors, if available

        Raises:
            APIError: If the API request fails
        """
        return _validate_rule(self, rule_text)

    def translate_nl_to_udm(self, text: str) -> str:
        """Translate natural language query to UDM search syntax.

        Args:
            text: Natural language query text

        Returns:
            UDM search query string

        Raises:
            APIError: If the API request fails
                or no valid query can be generated
        """
        return translate_nl_to_udm(self, text)

    def gemini(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        context_uri: str = "/search",
        context_body: Optional[Dict[str, Any]] = None,
    ) -> GeminiResponse:
        """Query Chronicle Gemini with a prompt.

        This method provides access to Chronicle's Gemini conversational
        AI interface, which can answer security questions, generate detection
        rules, explain CVEs, and provide other security insights.

        Args:
            query: The text query to send to Gemini
            conversation_id: Optional conversation ID. If not provided,
                a new conversation will be created
            context_uri: URI context for the query (default: "/search")
            context_body: Optional additional context as a dictionary

        Returns:
            A GeminiResponse object with structured content blocks
            (text, code, HTML) and suggested actions if applicable

        Raises:
            APIError: If the API request fails

        Example:
            ```python
            # Ask about a security concept
            response = chronicle.gemini("What is Windows event ID 4625?")

            # Get explanatory text
            print(response.get_text_content())

            # Get code blocks separately (for rule generation, etc.)
            for code_block in response.get_code_blocks():
                print(f"Code: {code_block.content}")
            ```
        """
        return _query_gemini(
            self,
            query=query,
            conversation_id=conversation_id,
            context_uri=context_uri,
            context_body=context_body,
        )

    def opt_in_to_gemini(self) -> bool:
        """Opt the user into Gemini (Duet AI) in Chronicle.

        This method updates the user's preferences to enable Duet AI chat,
        which is required before using the Gemini functionality. The Gemini
        method will attempt to do this automatically if needed, but this method
        allows for explicit opt-in.

        Returns:
            True if successful, False if permission error

        Raises:
            APIError: If the API request fails for a reason other
                than permissions

        Example:
            ```python
            # Explicitly opt in to Gemini before using it
            chronicle.opt_in_to_gemini()

            # Now use Gemini
            response = chronicle.gemini("What is Windows event ID 4625?")
            ```
        """
        # Set the opt-in attempted flag
        self._gemini_opt_in_attempted = True
        return _opt_in_to_gemini(self)

    def nl_search(
        self,
        text: str,
        start_time: datetime,
        end_time: datetime,
        max_events: int = 10000,
        case_insensitive: bool = True,
        max_attempts: int = 30,
    ) -> Dict[str, Any]:
        """Perform a search using natural language that is translated to UDM.

        Args:
            text: Natural language query text
            start_time: Search start time
            end_time: Search end time
            max_events: Maximum events to return
            case_insensitive: Whether to perform case-insensitive search
            max_attempts: Maximum number of polling attempts

        Returns:
            Dict containing the search results with events

        Raises:
            APIError: If the API request fails
        """
        return _nl_search(
            self,
            text=text,
            start_time=start_time,
            end_time=end_time,
            max_events=max_events,
            case_insensitive=case_insensitive,
            max_attempts=max_attempts,
        )

    def ingest_log(
        self,
        log_type: str,
        log_message: str,
        log_entry_time: Optional[datetime] = None,
        collection_time: Optional[datetime] = None,
        forwarder_id: Optional[str] = None,
        force_log_type: bool = False,
        namespace: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Ingest a log into Chronicle.

        Args:
            log_type: Chronicle log type (e.g., "OKTA", "WINDOWS", etc.)
            log_message: The raw log message to ingest
            log_entry_time: The time the log entry was created
                (defaults to current time)
            collection_time: The time the log was collected
                (defaults to current time)
            forwarder_id: ID of the forwarder to use
                (creates or uses default if None)
            force_log_type: Whether to force using the log type even
                if not in the valid list

        Returns:
            Dictionary containing the operation details for the ingestion

        Raises:
            ValueError: If the log type is invalid or timestamps are invalid
            APIError: If the API request fails
        """
        return _ingest_log(
            self,
            log_type=log_type,
            log_message=log_message,
            log_entry_time=log_entry_time,
            collection_time=collection_time,
            forwarder_id=forwarder_id,
            force_log_type=force_log_type,
            namespace=namespace,
            labels=labels,
        )

    def get_or_create_forwarder(
        self, display_name: str = "Wrapper-SDK-Forwarder"
    ) -> Dict[str, Any]:
        """Get an existing forwarder by name or create a new one if none exists.

        Args:
            display_name: Name of the forwarder to find or create

        Returns:
            Dictionary containing the forwarder details

        Raises:
            APIError: If the API request fails
        """
        return _get_or_create_forwarder(self, display_name=display_name)

    def get_all_log_types(self) -> List[LogType]:
        """Get all available Chronicle log types.

        Returns:
            List of LogType objects representing all available log types
        """
        return _get_all_log_types()

    def is_valid_log_type(self, log_type_id: str) -> bool:
        """Check if a log type ID is valid.

        Args:
            log_type_id: The log type ID to validate

        Returns:
            True if the log type exists, False otherwise
        """
        return _is_valid_log_type(log_type_id)

    def get_log_type_description(self, log_type_id: str) -> Optional[str]:
        """Get the description for a log type ID.

        Args:
            log_type_id: The log type ID to get the description for

        Returns:
            Description string if the log type exists, None otherwise
        """
        return _get_log_type_description(log_type_id)

    def search_log_types(
        self,
        search_term: str,
        case_sensitive: bool = False,
        search_in_description: bool = True,
    ) -> List[LogType]:
        """Search log types by ID or description.

        Args:
            search_term: Term to search for
            case_sensitive: Whether the search should be case sensitive
            search_in_description: Whether to search in descriptions
                as well as IDs

        Returns:
            List of matching LogType objects
        """
        return _search_log_types(
            search_term, case_sensitive, search_in_description
        )

    def ingest_udm(
        self,
        udm_events: Union[Dict[str, Any], List[Dict[str, Any]]],
        add_missing_ids: bool = True,
    ) -> Dict[str, Any]:
        """Ingest UDM events directly into Chronicle.

        Args:
            udm_events: A single UDM event dictionary or a list of UDM
                event dictionaries
            add_missing_ids: Whether to automatically add unique IDs to
                events missing them

        Returns:
            Dictionary containing the operation details for the ingestion

        Raises:
            ValueError: If any required fields are missing or events are
                malformed
            APIError: If the API request fails
        """
        return _ingest_udm(
            self, udm_events=udm_events, add_missing_ids=add_missing_ids
        )

    def get_data_export(self, data_export_id: str) -> Dict[str, Any]:
        """Get information about a specific data export.

        Args:
            data_export_id: ID of the data export to retrieve

        Returns:
            Dictionary containing data export details

        Raises:
            APIError: If the API request fails

        Example:
            ```python
            export = chronicle.get_data_export("export123")
            print(f"Export status: {export['data_export_status']['stage']}")
            ```
        """
        return _get_data_export(self, data_export_id)

    def create_data_export(
        self,
        gcs_bucket: str,
        start_time: datetime,
        end_time: datetime,
        log_type: Optional[str] = None,
        export_all_logs: bool = False,
    ) -> Dict[str, Any]:
        """Create a new data export job.

        Args:
            gcs_bucket: GCS bucket path in format
                "projects/{project}/buckets/{bucket}"
            start_time: Start time for the export (inclusive)
            end_time: End time for the export (exclusive)
            log_type: Optional specific log type to export.
                If None and export_all_logs is False, no logs will be exported
            export_all_logs: Whether to export all log types

        Returns:
            Dictionary containing details of the created data export

        Raises:
            APIError: If the API request fails
            ValueError: If invalid parameters are provided

        Example:
            ```python
            from datetime import datetime, timedelta

            end_time = datetime.now()
            start_time = end_time - timedelta(days=1)

            # Export a specific log type
            export = chronicle.create_data_export(
                gcs_bucket="projects/my-project/buckets/my-bucket",
                start_time=start_time,
                end_time=end_time,
                log_type="WINDOWS"
            )

            # Export all logs
            export = chronicle.create_data_export(
                gcs_bucket="projects/my-project/buckets/my-bucket",
                start_time=start_time,
                end_time=end_time,
                export_all_logs=True
            )
            ```
        """
        return _create_data_export(
            self,
            gcs_bucket=gcs_bucket,
            start_time=start_time,
            end_time=end_time,
            log_type=log_type,
            export_all_logs=export_all_logs,
        )

    def cancel_data_export(self, data_export_id: str) -> Dict[str, Any]:
        """Cancel an in-progress data export.

        Args:
            data_export_id: ID of the data export to cancel

        Returns:
            Dictionary containing details of the cancelled data export

        Raises:
            APIError: If the API request fails

        Example:
            ```python
            result = chronicle.cancel_data_export("export123")
            print("Export cancellation request submitted")
            ```
        """
        return _cancel_data_export(self, data_export_id)

    def fetch_available_log_types(
        self,
        start_time: datetime,
        end_time: datetime,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch available log types for export within a time range.

        Args:
            start_time: Start time for the time range (inclusive)
            end_time: End time for the time range (exclusive)
            page_size: Optional maximum number of results to return
            page_token: Optional page token for pagination

        Returns:
            Dictionary containing:
                - available_log_types: List of AvailableLogType objects
                - next_page_token: Token for fetching the next page of results

        Raises:
            APIError: If the API request fails
            ValueError: If invalid parameters are provided

        Example:
            ```python
            from datetime import datetime, timedelta

            end_time = datetime.now()
            start_time = end_time - timedelta(days=7)

            result = chronicle.fetch_available_log_types(
                start_time=start_time,
                end_time=end_time
            )

            for log_type in result["available_log_types"]:
                print(f"{log_type.display_name} ({log_type.log_type})")
                print(
                    f"  Available from {log_type.start_time} to "
                    f"{log_type.end_time}"
                )
            ```
        """
        return _fetch_available_log_types(
            self,
            start_time=start_time,
            end_time=end_time,
            page_size=page_size,
            page_token=page_token,
        )

    # Data Table methods

    def create_data_table(
        self,
        name: str,
        description: str,
        header: Dict[str, DataTableColumnType],
        rows: Optional[List[List[str]]] = None,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new data table.

        Args:
            name: The name for the new data table
            description: A user-provided description of the data table
            header: A dictionary mapping column names to column types
            rows: Optional list of rows for the data table
            scopes: Optional list of scopes for the data table

        Returns:
            Dictionary containing the created data table

        Raises:
            APIError: If the API request fails
            SecOpsError: If the data table name is invalid
                or CIDR validation fails
        """
        return _create_data_table(self, name, description, header, rows, scopes)

    def get_data_table(self, name: str) -> Dict[str, Any]:
        """Get data table details.

        Args:
            name: The name of the data table to get

        Returns:
            Dictionary containing the data table

        Raises:
            APIError: If the API request fails
        """
        return _get_data_table(self, name)

    def list_data_tables(
        self, order_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List data tables.

        Args:
            order_by: Configures ordering of DataTables in the response.
                      Note: The API only supports "createTime asc".

        Returns:
            List of data tables

        Raises:
            APIError: If the API request fails
        """
        return _list_data_tables(self, order_by)

    def delete_data_table(
        self, name: str, force: bool = False
    ) -> Dict[str, Any]:
        """Delete a data table.

        Args:
            name: The name of the data table to delete
            force: If set to true, any rows under this data table will
                also be deleted. (Otherwise, the request will only work
                if the data table has no rows).

        Returns:
            Dictionary containing the deleted data table or empty dict

        Raises:
            APIError: If the API request fails
        """
        return _delete_data_table(self, name, force)

    def create_data_table_rows(
        self, name: str, rows: List[List[str]]
    ) -> List[Dict[str, Any]]:
        """Create data table rows, chunking if necessary.

        Args:
            name: The name of the data table
            rows: A list of rows for the data table

        Returns:
            List of responses containing the created data table rows

        Raises:
            APIError: If the API request fails
            SecOpsError: If a row is too large to process
        """
        return _create_data_table_rows(self, name, rows)

    def list_data_table_rows(
        self, name: str, order_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List data table rows.

        Args:
            name: The name of the data table to list rows from
            order_by: Configures ordering of DataTableRows in the response.
                      Note: The API only supports "createTime asc".

        Returns:
            List of data table rows

        Raises:
            APIError: If the API request fails
        """
        return _list_data_table_rows(self, name, order_by)

    def delete_data_table_rows(
        self, name: str, row_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """Delete data table rows.

        Args:
            name: The name of the data table to delete rows from
            row_ids: The IDs of the rows to delete

        Returns:
            List of dictionaries containing the deleted data table rows

        Raises:
            APIError: If the API request fails
        """
        return _delete_data_table_rows(self, name, row_ids)

    # Reference List methods

    def create_reference_list(
        self,
        name: str,
        description: str = "",
        entries: List[str] = None,
        syntax_type: ReferenceListSyntaxType = ReferenceListSyntaxType.STRING,
    ) -> Dict[str, Any]:
        """Create a new reference list.

        Args:
            name: The name for the new reference list
            description: A user-provided description of the reference list
            entries: A list of entries for the reference list
            syntax_type: The syntax type of the reference list

        Returns:
            Dictionary containing the created reference list

        Raises:
            APIError: If the API request fails
            SecOpsError: If the reference list name is invalid or
                a CIDR entry is invalid
        """
        # Defaulting to empty string
        if entries is None:
            entries = []

        return _create_reference_list(
            self, name, description, entries, syntax_type
        )

    def get_reference_list(
        self, name: str, view: ReferenceListView = ReferenceListView.FULL
    ) -> Dict[str, Any]:
        """Get a single reference list.

        Args:
            name: The name of the reference list
            view: How much of the ReferenceList to view.
                Defaults to REFERENCE_LIST_VIEW_FULL.

        Returns:
            Dictionary containing the reference list

        Raises:
            APIError: If the API request fails
        """
        return _get_reference_list(self, name, view)

    def list_reference_lists(
        self,
        view: ReferenceListView = ReferenceListView.BASIC,
    ) -> List[Dict[str, Any]]:
        """List reference lists.

        Args:
            view: How much of each ReferenceList to view.
                Defaults to REFERENCE_LIST_VIEW_BASIC.

        Returns:
            List of reference lists, ordered in ascending
            alphabetical order by name

        Raises:
            APIError: If the API request fails
        """
        return _list_reference_lists(self, view)

    def update_reference_list(
        self,
        name: str,
        description: Optional[str] = None,
        entries: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update a reference list.

        Args:
            name: The name of the reference list
            description: A user-provided description of the reference list
            entries: A list of entries for the reference list

        Returns:
            Dictionary containing the updated reference list

        Raises:
            APIError: If the API request fails
            SecOpsError: If no description or entries are provided to be updated
        """
        return _update_reference_list(self, name, description, entries)
