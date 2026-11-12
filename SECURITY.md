# Security policy

## Supported versions

Security fixes are made on the latest release, which the moving major tag (for example
`v1`) points to. Older releases are not patched separately.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use GitHub's private
vulnerability reporting: open the **Security** tab and choose **Report a vulnerability**.
Include the affected version, reproduction steps, and the impact you observed.
We will acknowledge the report, work on a fix, and coordinate disclosure with you.

You can also email [reports@kalanos.ai](mailto:reports@kalanos.ai). Email is not encrypted,
so use the GitHub advisory for sensitive technical detail.

Never include credentials, private reports or private datasets in a report.

## Scope

In scope: the wrapper script, `action.yml` and the workflows in this repository.
Issues in the Kalanos grader itself belong to [KalanosAI/kalanos](https://github.com/KalanosAI/kalanos);
send them through the same private channels and they will be routed.

For what this Action does and does not isolate, read the "Privacy and runner security"
section of the [README](README.md#privacy-and-runner-security).
