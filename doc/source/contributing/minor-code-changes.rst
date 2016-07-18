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

Tests
-----

Occasionally someone proposes a patch that converts instances of
``assertEqual(True, whatever)`` to ``assertTrue(whatever)``, or instances of
``asertEqual(False, w)`` to ``assertFalse(w)`` in tests.  Note that these are
not type safe changes and they weaken the tests.  (See the Python ``unittest``
docs for details.)  We tend to be very conservative about our tests and don't
like weakening changes.

We're not saying that such changes can never be made, we're just saying that
each change must be accompanied by an explanation of why the weaker test is
adequate for what's being tested.

LOG.warn to LOG.warning
-----------------------

Consistently there are proposed changes that will change all {LOG,logging}.
warn to {LOG,logging}.warning across the codebase due to the deprecation in
Python 3. While the deprecation is real, Glance uses oslo_log that provides
alias warn and solves the issue in single place for all projects using it.
These changes are not accepted due to the huge amount of refactoring they
cause for no reason.
