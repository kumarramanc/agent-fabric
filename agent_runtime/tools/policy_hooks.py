"""Post-processing for policy versions, separate from tool execution."""

import datetime as datetime_lib


class CurrentPoliciesHook:
    def __init__(self, current_date):
        self.current_date = datetime_lib.date.fromisoformat(current_date)

    def __call__(self, output):
        # If a requested policy was not found, do not return an incomplete rule set.
        if output.get("missing_policies"):
            return {
                "policies": [],
                "error": "Some requested policies could not be found.",
                "policy_names": output["missing_policies"]
            }

        versions_by_name = {}

        # 1. Read the EFFECTIVE DATE from each document, not its folder name.
        for policy in output["policies"]:
            date_lines = []
            for line in policy["text"].splitlines():
                if line.startswith("EFFECTIVE DATE:"):
                    date_lines.append(line)

            if len(date_lines) != 1:
                return self.policy_error(policy, "Expected one EFFECTIVE DATE header.")

            date_text = date_lines[0].split(":", 1)[1].strip()
            try:
                effective_date = datetime_lib.date.fromisoformat(date_text)
                if effective_date.isoformat() != date_text:
                    raise ValueError("Expected YYYY-MM-DD.")
            except ValueError:
                return self.policy_error(policy, "Invalid effective date; expected YYYY-MM-DD.")

            policy_name = policy["policy_name"]
            if policy_name not in versions_by_name:
                versions_by_name[policy_name] = []

            # Future documents do not apply to the simulation date.
            if effective_date <= self.current_date:
                version = dict(policy)
                version["effective_date"] = effective_date.isoformat()
                versions_by_name[policy_name].append(version)

        # 2. Select the newest effective document separately for each policy name.
        selected_policies = []
        for policy_name, versions in versions_by_name.items():
            if len(versions) == 0:
                return {
                    "policies": [],
                    "error": "No version is effective yet for a requested policy.",
                    "policy_name": policy_name
                }

            newest_date = max(version["effective_date"] for version in versions)
            latest_versions = []
            for version in versions:
                if version["effective_date"] == newest_date:
                    latest_versions.append(version)

            selected = latest_versions[0]
            for version in latest_versions[1:]:
                # Identical copies are safe to collapse; conflicting copies are not.
                if version["text"].strip() != selected["text"].strip():
                    return {
                        "policies": [],
                        "error": "Conflicting policy versions have the same effective date.",
                        "policy_name": policy_name,
                        "effective_date": newest_date
                    }

                # For identical top-level/versioned copies, show the versioned path.
                # This only resolves duplicate copies, never which date is current.
                if "/" not in selected["source_path"] and "/" in version["source_path"]:
                    selected = version

            selected_policies.append(selected)

        # 3. Return only the selected documents to the model.
        return {"policies": selected_policies}

    def policy_error(self, policy, message):
        return {
            "policies": [],
            "error": message,
            "policy_name": policy["policy_name"],
            "source_path": policy["source_path"]
        }
