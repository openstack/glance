glance Style Commandments
=======================

- Step 1: Read the OpenStack Style Commandments
  http://docs.openstack.org/developer/hacking/
- Step 2: Read on

glance Specific Commandments
--------------------------

- [G316] Change assertTrue(isinstance(A, B)) by optimal assert like
  assertIsInstance(A, B)
- [G317] Change assertEqual(type(A), B) by optimal assert like
  assertIsInstance(A, B)
- [G318] Change assertEqual(A, None) or assertEqual(None, A) by optimal assert like
  assertIsNone(A)
- [G319] Validate that debug level logs are not translated
- [G320] For python 3 compatibility, use six.text_type() instead of unicode()
