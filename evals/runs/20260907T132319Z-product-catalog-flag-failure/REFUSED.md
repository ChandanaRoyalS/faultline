# Refused run

**Reason:** model unreachable

**Nothing was injected and this scenario was not attempted.** This is not a discard: a discard is a run that happened and produced no result. Recorded rather than deleted, so a refusal that recurs is visible as a pattern.

the configured model (claude-opus-5) could not be reached or billed.
  "Could not resolve authentication method. Expected one of api_key, auth_token, or credentials to be set. Or for one of the `X-Api-Key` or `Authorization` headers to be explicitly omitted"
Nothing was injected and the world is untouched. This is not a discard - the run
never started, and counting it as one would inflate a number kept honest on purpose.
Dev sweep 8 injected the same scenario four times before discovering this at the
triage call; the check that would have caught it costs one token (Q20).
