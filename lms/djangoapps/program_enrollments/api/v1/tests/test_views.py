"""
Unit tests for ProgramEnrollment views.
"""
from __future__ import unicode_literals

import mock

from django.urls import reverse
from opaque_keys.edx.keys import CourseKey
from rest_framework import status
from rest_framework.test import APITestCase
from six import text_type

from lms.djangoapps.courseware.tests.factories import GlobalStaffFactory
from lms.djangoapps.program_enrollments.models import ProgramCourseEnrollment, ProgramEnrollment
from openedx.core.djangoapps.content.course_overviews.tests.factories import CourseOverviewFactory
from student.tests.factories import UserFactory

from .factories import ProgramCourseEnrollmentFactory, ProgramEnrollmentFactory


class ListViewTestMixin(object):
    """
    Mixin to define some shared test data objects for program/course enrollment
    list view tests.
    """
    view_name = None

    @classmethod
    def setUpClass(cls):
        super(ListViewTestMixin, cls).setUpClass()
        cls.program_uuid = '00000000-1111-2222-3333-444444444444'
        cls.curriculum_uuid = 'aaaaaaaa-1111-2222-3333-444444444444'
        cls.other_curriculum_uuid = 'bbbbbbbb-1111-2222-3333-444444444444'

        cls.course_id = CourseKey.from_string('course-v1:edX+ToyX+Toy_Course')
        _ = CourseOverviewFactory.create(id=cls.course_id)

        cls.password = 'password'
        cls.student = UserFactory.create(username='student', password=cls.password)
        cls.global_staff = GlobalStaffFactory.create(username='global-staff', password=cls.password)

    @classmethod
    def tearDownClass(cls):
        super(ListViewTestMixin, cls).tearDownClass()

    def get_url(self, program_key=None, course_id=None):
        """ Returns the primary URL requested by the test case. """
        kwargs = {'program_key': program_key or self.program_uuid}
        if course_id:
            kwargs['course_id'] = course_id or self.course_id

        return reverse(self.view_name, kwargs=kwargs)


class ProgramEnrollmentListTest(ListViewTestMixin, APITestCase):
    """
    Tests for GET calls to the Program Enrollments API.
    """
    view_name = 'programs_api:v1:program_enrollments'

    def create_program_enrollments(self):
        """
        Helper method for creating program enrollment records.
        """
        for i in xrange(2):
            user_key = 'user-{}'.format(i)
            ProgramEnrollmentFactory.create(
                program_uuid=self.program_uuid,
                curriculum_uuid=self.curriculum_uuid,
                user=None,
                status='pending',
                external_user_key=user_key,
            )

        for i in xrange(2, 4):
            user_key = 'user-{}'.format(i)
            ProgramEnrollmentFactory.create(
                program_uuid=self.program_uuid, curriculum_uuid=self.curriculum_uuid, external_user_key=user_key,
            )

        self.addCleanup(self.destroy_program_enrollments)

    def destroy_program_enrollments(self):
        """
        Deletes program enrollments associated with this test case's program_uuid.
        """
        ProgramEnrollment.objects.filter(program_uuid=self.program_uuid).delete()

    @mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True, return_value=None)
    def test_404_if_no_program_with_key(self, mock_get_programs):
        self.client.login(username=self.global_staff.username, password=self.password)
        response = self.client.get(self.get_url(self.program_uuid))
        assert status.HTTP_404_NOT_FOUND == response.status_code
        mock_get_programs.assert_called_once_with(uuid=self.program_uuid)

    def test_403_if_not_staff(self):
        self.client.login(username=self.student.username, password=self.password)
        response = self.client.get(self.get_url(self.program_uuid))
        assert status.HTTP_403_FORBIDDEN == response.status_code

    def test_401_if_anonymous(self):
        response = self.client.get(self.get_url(self.program_uuid))
        assert status.HTTP_401_UNAUTHORIZED == response.status_code

    def test_200_empty_results(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            response = self.client.get(self.get_url(self.program_uuid))

        assert status.HTTP_200_OK == response.status_code
        expected = {
            'next': None,
            'previous': None,
            'results': [],
        }
        assert expected == response.data

    def test_200_many_results(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        self.create_program_enrollments()
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            response = self.client.get(self.get_url(self.program_uuid))

        assert status.HTTP_200_OK == response.status_code
        expected = {
            'next': None,
            'previous': None,
            'results': [
                {
                    'student_key': 'user-0', 'status': 'pending', 'account_exists': False,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-1', 'status': 'pending', 'account_exists': False,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-2', 'status': 'enrolled', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-3', 'status': 'enrolled', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
            ],
        }
        assert expected == response.data

    def test_200_many_pages(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        self.create_program_enrollments()
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            url = self.get_url(self.program_uuid) + '?page_size=2'
            response = self.client.get(url)

            assert status.HTTP_200_OK == response.status_code
            expected_results = [
                {
                    'student_key': 'user-0', 'status': 'pending', 'account_exists': False,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-1', 'status': 'pending', 'account_exists': False,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
            ]
            assert expected_results == response.data['results']
            # there's going to be a 'cursor' query param, but we have no way of knowing it's value
            assert response.data['next'] is not None
            assert self.get_url(self.program_uuid) in response.data['next']
            assert '?cursor=' in response.data['next']
            assert response.data['previous'] is None

            next_response = self.client.get(response.data['next'])
            assert status.HTTP_200_OK == next_response.status_code
            next_expected_results = [
                {
                    'student_key': 'user-2', 'status': 'enrolled', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-3', 'status': 'enrolled', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
            ]
            assert next_expected_results == next_response.data['results']
            assert next_response.data['next'] is None
            # there's going to be a 'cursor' query param, but we have no way of knowing it's value
            assert next_response.data['previous'] is not None
            assert self.get_url(self.program_uuid) in next_response.data['previous']
            assert '?cursor=' in next_response.data['previous']


class ProgramCourseEnrollmentListTest(ListViewTestMixin, APITestCase):
    """
    Tests for GET calls to the Program Course Enrollments API.
    """
    view_name = 'programs_api:v1:program_course_enrollments'

    def create_course_enrollments(self):
        """ Helper method for creating ProgramCourseEnrollments. """
        program_enrollment_1 = ProgramEnrollmentFactory.create(
            program_uuid=self.program_uuid, curriculum_uuid=self.curriculum_uuid, external_user_key='user-0',
        )
        program_enrollment_2 = ProgramEnrollmentFactory.create(
            program_uuid=self.program_uuid, curriculum_uuid=self.other_curriculum_uuid, external_user_key='user-0',
        )
        ProgramCourseEnrollmentFactory.create(
            program_enrollment=program_enrollment_1,
            course_key=self.course_id,
            status='active',
        )
        ProgramCourseEnrollmentFactory.create(
            program_enrollment=program_enrollment_2,
            course_key=self.course_id,
            status='inactive',
        )

        self.addCleanup(self.destroy_course_enrollments)

    def destroy_course_enrollments(self):
        """ Helper method for tearing down ProgramCourseEnrollments. """
        ProgramCourseEnrollment.objects.filter(
            program_enrollment__program_uuid=self.program_uuid,
            course_key=self.course_id
        ).delete()

    @mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True, return_value=None)
    def test_404_if_no_program_with_key(self, mock_get_programs):
        self.client.login(username=self.global_staff.username, password=self.password)
        response = self.client.get(self.get_url(self.program_uuid, self.course_id))
        assert status.HTTP_404_NOT_FOUND == response.status_code
        mock_get_programs.assert_called_once_with(uuid=self.program_uuid)

    def test_404_if_course_does_not_exist(self):
        other_course_key = CourseKey.from_string('course-v1:edX+ToyX+Other_Course')
        self.client.login(username=self.global_staff.username, password=self.password)
        response = self.client.get(self.get_url(self.program_uuid, other_course_key))
        assert status.HTTP_404_NOT_FOUND == response.status_code

    def test_403_if_not_staff(self):
        self.client.login(username=self.student.username, password=self.password)
        response = self.client.get(self.get_url(self.program_uuid, self.course_id))
        assert status.HTTP_403_FORBIDDEN == response.status_code

    def test_401_if_anonymous(self):
        response = self.client.get(self.get_url(self.program_uuid, self.course_id))
        assert status.HTTP_401_UNAUTHORIZED == response.status_code

    def test_200_empty_results(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            response = self.client.get(self.get_url(self.program_uuid, self.course_id))

        assert status.HTTP_200_OK == response.status_code
        expected = {
            'next': None,
            'previous': None,
            'results': [],
        }
        assert expected == response.data

    def test_200_many_results(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        self.create_course_enrollments()
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            response = self.client.get(self.get_url(self.program_uuid, self.course_id))

        assert status.HTTP_200_OK == response.status_code
        expected = {
            'next': None,
            'previous': None,
            'results': [
                {
                    'student_key': 'user-0', 'status': 'active', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
                {
                    'student_key': 'user-0', 'status': 'inactive', 'account_exists': True,
                    'curriculum_uuid': text_type(self.other_curriculum_uuid),
                },
            ],
        }
        assert expected == response.data

    def test_200_many_pages(self):
        self.client.login(username=self.global_staff.username, password=self.password)

        self.create_course_enrollments()
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            url = self.get_url(self.program_uuid, self.course_id) + '?page_size=1'
            response = self.client.get(url)

            assert status.HTTP_200_OK == response.status_code
            expected_results = [
                {
                    'student_key': 'user-0', 'status': 'active', 'account_exists': True,
                    'curriculum_uuid': text_type(self.curriculum_uuid),
                },
            ]
            assert expected_results == response.data['results']
            # there's going to be a 'cursor' query param, but we have no way of knowing it's value
            assert response.data['next'] is not None
            assert self.get_url(self.program_uuid, self.course_id) in response.data['next']
            assert '?cursor=' in response.data['next']
            assert response.data['previous'] is None

            next_response = self.client.get(response.data['next'])
            assert status.HTTP_200_OK == next_response.status_code
            next_expected_results = [
                {
                    'student_key': 'user-0', 'status': 'inactive', 'account_exists': True,
                    'curriculum_uuid': text_type(self.other_curriculum_uuid),
                },
            ]
            assert next_expected_results == next_response.data['results']
            assert next_response.data['next'] is None
            # there's going to be a 'cursor' query param, but we have no way of knowing it's value
            assert next_response.data['previous'] is not None
            assert self.get_url(self.program_uuid, self.course_id) in next_response.data['previous']
            assert '?cursor=' in next_response.data['previous']
