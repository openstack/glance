glance Style Commandments
=========================

- Step 1: Read the OpenStack Style Commandments
  https://docs.openstack.org/hacking/latest/
- Step 2: Read on

glance Specific Commandments
----------------------------

- [G316] Change assertTrue(isinstance(A, B)) by optimal assert like
  assertIsInstance(A, B)
- [G317] Change assertEqual(type(A), B) by optimal assert like
  assertIsInstance(A, B)
- [G318] Change assertEqual(A, None) or assertEqual(None, A) by optimal assert
  like assertIsNone(A)
- [G319] Validate that debug level logs are not translated
- [G327] Prevent use of deprecated contextlib.nested
- [G328] Must use a dict comprehension instead of a dict constructor with
  a sequence of key-value pairs
- [G330] Log.warn is deprecated. Enforce use of LOG.warning.
