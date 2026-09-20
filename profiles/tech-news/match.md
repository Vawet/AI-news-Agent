Decide whether each indexed news item should use this scoring profile.

Profile: {profile_name}
Description: {profile_description}

This profile is for business AI Agent developers. Match items about reusable
harness methodology (context, tools, memory, orchestration, evals, observability,
security, sandboxes), usable shipped model capabilities, highly relevant
GitHub-trending agent OSS, or evidence-backed official frontier-lab writing about
agents and product use.

Do not match pre-training, post-training, RLHF, architecture-training papers,
generic benchmark announcements without reusable methodology, thin wrappers,
demo repositories, or official PR without concrete engineering insight.

Return only a JSON object containing the matching input indexes:
{{"indexes":[0,2,3]}}

Items:
{items}
