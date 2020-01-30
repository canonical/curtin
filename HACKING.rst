*****************
Hacking on curtin
*****************

This document describes how to contribute changes to curtin.
It assumes you have a `Launchpad`_ account, and refers to your launchpad user
as ``LP_USER`` throughout.

Do these things once
====================

* To contribute, you must sign the Canonical `contributor license agreement`_

  If you have already signed it as an individual, your Launchpad user will
  be listed in the `contributor-agreement-canonical`_ group.  Unfortunately
  there is no easy way to check if an organization or company you are doing
  work for has signed.  If you are unsure or have questions, email
  `Josh Powers <mailto:josh.powers@canonical.com>` or ping powersj in
  ``#curtin`` channel via Freenode IRC.

  When prompted for 'Project contact' or 'Canonical Project Manager' enter
  'Josh Powers'.

* Configure git with your email and name for commit messages.

  Your name will appear in commit messages and will also be used in
  changelogs or release notes.  Give yourself credit! Please provide
  a valid email address::

    git config user.name "Your Name"
    git config user.email "Your Email"

* Clone the upstream `repository`_ on Launchpad::

    git clone https://git.launchpad.net/curtin
    cd curtin

  There is more information on Launchpad as a git hosting site in
  `Launchpad git documentation`_.

* Create a new remote pointing to your personal Launchpad repository.
  This is equivalent to 'fork' on github.

  .. code:: sh

    git remote add LP_USER ssh://LP_USER@git.launchpad.net/~LP_USER/curtin
    git push LP_USER master

.. _repository: https://git.launchpad.net/curtin
.. _contributor license agreement: http://www.canonical.com/contributors
.. _contributor-agreement-canonical: https://launchpad.net/%7Econtributor-agreement-canonical/+members
.. _Launchpad git documentation: https://help.launchpad.net/Code/Git

Do these things for each feature or bug
=======================================

* Create a new topic branch for your work::

    git checkout -b my-topic-branch

* Make and commit your changes (note, you can make multiple commits,
  fixes, more commits.)::

    git commit

* Run unit tests and lint/formatting checks with `tox`_::

    tox

* Push your changes to your personal Launchpad repository::

    git push -u LP_USER my-topic-branch

* Use your browser to create a merge request:

  - Open the branch on Launchpad.

    - You can see a web view of your repository and navigate to the branch at:

      ``https://code.launchpad.net/~LP_USER/curtin/``

    - It will typically be at:

      ``https://code.launchpad.net/~LP_USER/curtin/+git/curtin/+ref/BRANCHNAME``

      Here is an example link: https://code.launchpad.net/~raharper/curtin/+git/curtin/+ref/feature/zfs-root

  - Click 'Propose for merging'
  - Select 'lp:curtin' as the target repository
  - Type '``master``' as the Target reference path
  - Click 'Propose Merge'
  - On the next page, hit 'Set commit message' and type a combined git
    style commit message.

    The commit message should be one summary line of less than 74
    characters followed by a blank line, and then one or more paragraphs
    describing the change and why it was needed.

    If you have fixed a bug in your commit, reference it at the end of
    the message with ``LP: #XXXXXXX``.

    This is the message that will be used on the commit when it is
    sqaushed and merged into trunk. Here is an example: ::

      Activate the frobnicator.

      The frobnicator was previously inactive and now runs by default.
      This may save the world some day.  Then, list the bugs you fixed
      as footers with syntax as shown here.

      LP: #1

Then, someone in the `curtin-dev` group will review your changes and
follow up in the merge request.

Feel free to ping and/or join ``#curtin`` on Freenode IRC if you
have any questions.

.. _tox: https://tox.readthedocs.io/en/latest/
.. _Launchpad: https://launchpad.net
.. _curtin-dev: https://launchpad.net/~curtin-dev/+members#active
