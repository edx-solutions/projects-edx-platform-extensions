projects-edx-platform-extensions
================================

projects-edx-platform-extensions (``edx_solutions_projects``) is a Django application responsible for managing the concept of Projects in the Open edX platform. Projects are an intersection of Courses, CourseContent, and Workgroups. Projects application depends on organizations application so organizations application should be installed before installing edx_solutions_projects application.


Open edX Platform Integration
-----------------------------
1. Update the version of ``projects-edx-platform-extensions`` in the appropriate requirements file (e.g. ``requirements/edx/custom.txt``).
2. Add ``edx_solutions_projects`` to the list of installed apps in ``common.py``.
3. Install edx_solutions_projects app via requirements file

.. code-block:: bash
  $ pip install -r requirements/edx/custom.txt

4. (Optional) Run tests:

.. code-block:: bash

   $ paver test_system -s lms -t edx_solutions_projects

