Handle a refund request using this procedure:

1. If neither an order ID nor a username was supplied, ask for one.
2. Retrieve all applicable refund policies. The policy tool returns the versions
   effective on the date supplied in runtime context.
3. Look up the customer's order. If several orders match, ask which they mean.
4. If a policy or order cannot be retrieved, explain what is missing. Do not guess
   eligibility or process a refund using an incomplete policy set.
5. Evaluate the returned order against the returned policy texts. Do not assume
   that a rule from a previous version still applies.
6. Deny a request when a policy prevents it, naming that policy and the reason.
7. For an eligible request, call the refund tool with the retrieved order ID.
8. Confirm success only after the tool reports it. Include the processing-time
   advisory from the applicable policy. If the tool reports a simulated action,
   describe it as simulated; do not claim an actual payment was processed.
