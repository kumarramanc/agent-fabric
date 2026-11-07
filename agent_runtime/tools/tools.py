"""Customer support tools built on shared validation and post-hooks."""

import json as json_lib
import os as os_lib
import pydantic as pydantic_lib
import agent_runtime.tools.tool_utils as tool_helpers


# These models define both the Python inputs and the schemas sent to the LLM.
class SearchPoliciesInput(tool_helpers.ToolInput):
    policy_names: list[str] = pydantic_lib.Field(
        description="The policy filenames to retrieve."
    )


class OrderLookupInput(tool_helpers.ToolInput):
    order_id: str | None = pydantic_lib.Field(
        default=None, description="The customer-supplied order ID, or null."
    )
    username: str | None = pydantic_lib.Field(
        default=None, description="The customer-supplied username, or null."
    )


class RefundOrderInput(tool_helpers.ToolInput):
    order_id: str | None = pydantic_lib.Field(
        default=None, description="The ID of the order approved for refund, or null if missing."
    )


class SearchPoliciesTool(tool_helpers.Tool):
    """Retrieve matching policy documents from a folder and its subfolders."""

    def __init__(self, policies_dir, include_reason=False, post_hooks=None):
        self.policies_dir = os_lib.path.realpath(policies_dir)
        available_names = set()
        for folder, subfolders, names in os_lib.walk(self.policies_dir):
            for name in names:
                if name.endswith(".txt"):
                    available_names.add(name)
        super().__init__(
            name="search_policies",
            description=(
                "Read policy text by filename. Available policies: "
                + ", ".join(sorted(available_names)) + ". "
                "Read all applicable policies before deciding refund eligibility."
            ),
            input_model=SearchPoliciesInput,
            include_reason=include_reason,
            post_hooks=post_hooks
        )

    def read_policies(self, tool_args):
        # Keep the readable method name used in our earlier examples.
        return self(tool_args)

    def execute(self, arguments):
        # 1. Get the validated list of policy filenames.
        policy_names = arguments["policy_names"]

        # 2. Start with an empty list to hold the results.
        policies = []
        missing_policies = []
        processed_names = []

        # 3. Collect every version of each requested filename.
        for policy_name in policy_names:
            if os_lib.path.basename(policy_name) != policy_name or not policy_name.endswith(".txt"):
                raise ValueError("Supply policy .txt filenames, not folder paths.")
            if policy_name in processed_names:
                continue
            processed_names.append(policy_name)

            found = False
            for folder, subfolders, file_names in os_lib.walk(self.policies_dir):
                subfolders.sort()
                if policy_name not in file_names:
                    continue

                file_path = os_lib.path.join(folder, policy_name)
                resolved_path = os_lib.path.realpath(file_path)
                # Also reject symbolic links that lead outside the policy folder.
                if os_lib.path.commonpath([self.policies_dir, resolved_path]) != self.policies_dir:
                    raise ValueError("Choose a file inside the policy folder.")

                with open(resolved_path, encoding="utf-8") as file:
                    policy_text = file.read()

                policies.append({
                    "policy_name": policy_name,
                    "source_path": os_lib.path.relpath(file_path, self.policies_dir),
                    "text": policy_text
                })
                found = True

            if not found:
                missing_policies.append(policy_name)

        # 4. The attached post-hook selects the currently effective versions.
        output = {"policies": policies}
        if missing_policies:
            output["missing_policies"] = missing_policies
        return output


class OrderLookupTool(tool_helpers.Tool):
    """Find orders by order ID or username in the configured orders file."""

    def __init__(self, orders_path, include_reason=False, post_hooks=None):
        super().__init__(
            name="order_lookup",
            description=(
                "Look up orders by order ID or customer username. "
                "Supply the identifier the customer gave and use null for the other. "
                "If multiple orders match, ask which order the customer means. "
                "If neither identifier was supplied, ask for one."
            ),
            input_model=OrderLookupInput,
            include_reason=include_reason,
            post_hooks=post_hooks
        )
        self.orders_path = os_lib.path.realpath(orders_path)

    def lookup_order(self, tool_args):
        # Keep the readable method name used in our earlier examples.
        return self(tool_args)

    def execute(self, arguments):
        # 1. Get the validated identifiers.
        order_id = arguments.get("order_id")
        username = arguments.get("username")

        # Ask for an identifier if neither was supplied.
        if not order_id and not username:
            return {"message": "Please provide your order ID or username so I can look up your order."}

        # 2. Read the orders file into a list of dictionaries.
        with open(self.orders_path, encoding="utf-8") as file:
            orders = json_lib.load(file)

        # 3. Collect orders that match the supplied identifiers.
        matching_orders = []
        for order in orders:
            if order_id and order["order_id"] != order_id:
                continue
            if username and order["username"] != username:
                continue
            matching_orders.append(order)

        # 4. Return one order, several possible orders, or no match.
        if len(matching_orders) == 1:
            return {"order": matching_orders[0]}
        if len(matching_orders) > 1:
            return {"orders": matching_orders, "message": "Please specify which order you mean."}
        return {"error": "Order not found.", "order_id": order_id, "username": username}


class RefundOrderTool(tool_helpers.Tool):
    """Record a simulated refund after the agent checks policy eligibility."""

    def __init__(self, orders_path, current_date, include_reason=False, post_hooks=None):
        super().__init__(
            name="refund_order",
            description=(
                "Record a simulated refund in the configured orders file. "
                "Only call this after looking up the order and checking all "
                "applicable policies to confirm the refund is allowed. "
                "An order cannot be refunded twice."
            ),
            input_model=RefundOrderInput,
            include_reason=include_reason,
            post_hooks=post_hooks
        )
        self.orders_path = os_lib.path.realpath(orders_path)
        self.current_date = current_date

    def refund_order(self, tool_args):
        # Keep the readable method name used in our earlier examples.
        return self(tool_args)

    def execute(self, arguments):
        # 1. Get the validated order ID.
        order_id = arguments.get("order_id")

        if order_id is None or order_id == "":
            return {"message": "Please provide your order ID so I can process your refund."}

        # 2. Read all orders from the configured file.
        with open(self.orders_path, encoding="utf-8") as file:
            orders = json_lib.load(file)

        # 3. Find the requested order.
        for order in orders:
            if order["order_id"] == order_id:

                # 4. An order can only be refunded once.
                if order["refund_status"]:
                    return {"error": "This order has already been refunded.", "order": order}

                # 5. Record the refund. Eligibility is checked before calling this tool.
                order["refund_status"] = True
                order["refund_date"] = self.current_date

                # 6. Save the full list, including the updated order.
                with open(self.orders_path, "w", encoding="utf-8") as file:
                    json_lib.dump(orders, file, indent=2)

                # 7. Return the updated record.
                return {
                    "message": "Simulated refund recorded in the orders file.",
                    "order": order
                }

        return {"error": "Order not found.", "order_id": order_id}
