# Security reports

Use GitHub private vulnerability reporting where available, or contact
ivan@griffonix.com. Do not put private keys, tokens, personal media or private
adapter configuration in a public issue.

The adapter invokes the operator's configured SDK runner. That configuration and
the SDK kit are trusted administrative inputs; they must not be writable through
a public Comfy workflow or served from Comfy input/output/temp directories.
