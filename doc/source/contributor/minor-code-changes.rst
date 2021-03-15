Disallowed Minor Code Changes
=============================

There are a few types of code changes that have been proposed recently that
have been rejected by the Glance team, so we want to point them out and explain
our reasoning.

If you feel an exception should be made for some particular change, please put
it on the agenda for the Glance weekly meeting so it can be discussed.

Database migration scripts
--------------------------

Once a database script has been included in a release, spelling or grammar
corrections in comments are forbidden unless you are fixing them as a part of
another stronger bug on the migration script itself.  Modifying migration
scripts confuses operators and administrators -- we only want them to notice
serious problems.  Their preference must take precedence over fixing spell
errors.

Typographical errors in comments
--------------------------------

Comments are not user-facing.  Correcting minor misspellings or grammatical
errors only muddies the history of that part of the code, making ``git blame``
arguably less useful.  So such changes are likely to be rejected.  (This
prohibition, of course, does not apply to corrections of misleading or unclear
comments, or for example, an incorrect reference to a standards document.)

Misspellings in code
--------------------

Misspellings in function names are unlikely to be corrected for the "historical
clarity" reasons outlined above for comments.  Plus, if a function is named
``mispelled()`` and a later developer tries to call ``misspelled()``, the
latter will result in a NameError when it's called, so the later developer will
know to use the incorrectly spelled function name.

Misspellings in variable names are more problematic, because if you have a
variable named ``mispelled`` and a later developer puts up a patch where an
updated value is assigned to ``misspelled``, Python won't complain.  The "real"
variable won't be updated, and the patch won't have its intended effect.
Whether such a change is allowed will depend upon the age of the code, how
widely used the variable is, whether it's spelled correctly in other functions,
what the current test coverage is like, and so on.  We tend to be very
conservative about making changes that could cause regressions.  So whether a
patch that corrects the spelling of a variable name is accepted is a judgment
(or is that "judgement"?) call by reviewers.  In proposing your patch, however,
be aware that your reviewers will have these concerns in mind.

Tests
-----

Occasionally someone proposes a patch that converts instances of
``assertEqual(True, whatever)`` to ``assertTrue(whatever)``, or instances of
``assertEqual(False, w)`` to ``assertFalse(w)`` in tests.  Note that these are
not type safe changes and they weaken the tests.  (See the Python ``unittest``
docs for details.)  We tend to be very conservative about our tests and don't
like weakening changes.

We're not saying that such changes can never be made, we're just saying that
each change must be accompanied by an explanation of why the weaker test is
adequate for what's being tested.

Just to make this a bit clearer it can be shown using the following
example, comment out the lines in the runTest method alternatively::

  import unittest

  class MyTestCase(unittest.TestCase):
      def setUp(self):
          pass

  class Tests(MyTestCase):
      def runTest(self):
          self.assertTrue('True')
          self.assertTrue(True)
          self.assertEqual(True, 'True')

To run this use::

  python -m testtools.run test.py

Also mentioned within the unittests documentation_.

.. _documentation: https://docs.python.org/3/library/unittest.html#unittest.TestCase.assertTrue

LOG.warn to LOG.warning
-----------------------

Consistently there are proposed changes that will change all {LOG,logging}.
warn to {LOG,logging}.warning across the codebase due to the deprecation in
Python 3. While the deprecation is real, Glance uses oslo_log that provides
alias warn and solves the issue in single place for all projects using it.
These changes are not accepted due to the huge amount of refactoring they
cause for no reason.

Gratuitous use of oslo libraries
--------------------------------

We are big fans of the oslo libraries and all the hard work the Oslo team does
to keep common code reusable and easily consumable.  But that doesn't mean that
it's a bug if Glance isn't using an oslo library everywhere you could possibly
use one.  We are all for using oslo if it provides any level of benefit for us
and makes sense, but please let's not have these bugs/patches of "Let's use
oslo because it exists".


