"""
Unit tests for ProgramEnrollment views.
"""
from __future__ import unicode_literals

import json
from uuid import uuid4

import mock
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase
from six import text_type

from lms.djangoapps.courseware.tests.factories import GlobalStaffFactory
from lms.djangoapps.program_enrollments.models import ProgramEnrollment
from student.tests.factories import UserFactory

from .factories import ProgramEnrollmentFactory


class ProgramEnrollmentListTest(APITestCase):
    """
    Tests for GET calls to the Program Enrollments API.
    """
    @classmethod
    def setUpClass(cls):
        super(ProgramEnrollmentListTest, cls).setUpClass()
        cls.program_uuid = '00000000-1111-2222-3333-444444444444'
        cls.curriculum_uuid = 'aaaaaaaa-1111-2222-3333-444444444444'
        cls.password = 'password'
        cls.student = UserFactory.create(username='student', password=cls.password)
        cls.global_staff = GlobalStaffFactory.create(username='global-staff', password=cls.password)

    @classmethod
    def tearDownClass(cls):
        super(ProgramEnrollmentListTest, cls).tearDownClass()

    def create_enrollments(self):
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

        self.addCleanup(self.destroy_enrollments)

    def destroy_enrollments(self):
        """
        Deletes program enrollments associated with this test case's program_uuid.
        """
        ProgramEnrollment.objects.filter(program_uuid=self.program_uuid).delete()

    def get_url(self, program_key=None):
        return reverse('programs_api:v1:program_enrollments', kwargs={'program_key': program_key})

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

        self.create_enrollments()
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

        self.create_enrollments()
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


class ProgramEnrollmentViewPostTests(APITestCase):
    """
    Tests for the ProgramEnrollment view POST method.
    """
    def setUp(self):
        super(ProgramEnrollmentViewPostTests, self).setUp()
        global_staff = GlobalStaffFactory.create(username='global-staff', password='password')
        self.client.login(username=global_staff.username, password='password')

    def student_enrollment(self, enrollment_status, external_user_key=None):
        return {
            'status': enrollment_status,
            'external_user_key': external_user_key or str(uuid4().hex[0:10]),
            'curriculum_uuid': str(uuid4())
        }

    def test_successful_program_enrollments_no_existing_user(self):
        program_key = uuid4()
        statuses = ['pending', 'enrolled', 'pending']
        external_user_keys = ['abc1', 'efg2', 'hij3']

        curriculum_uuid = uuid4()
        curriculum_uuids = [curriculum_uuid, curriculum_uuid, uuid4()]
        post_data = [
            {
                'external_user_key': e,
                'status': s,
                'curriculum_uuid': str(c)
            }
            for e, s, c in zip(external_user_keys, statuses, curriculum_uuids)
        ]

        url = reverse('programs_api:v1:program_enrollments', args=[program_key])
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            with mock.patch(
                'lms.djangoapps.program_enrollments.api.v1.views.get_user_by_program_id',
                autospec=True,
                return_value=None
            ):
                response = self.client.post(url, json.dumps(post_data), content_type='application/json')

        self.assertEqual(response.status_code, 201)

        for i in range(3):
            enrollment = ProgramEnrollment.objects.filter(external_user_key=external_user_keys[i])[0]

            self.assertEqual(enrollment.external_user_key, external_user_keys[i])
            self.assertEqual(enrollment.program_uuid, program_key)
            self.assertEqual(enrollment.status, statuses[i])
            self.assertEqual(enrollment.curriculum_uuid, curriculum_uuids[i])
            self.assertEqual(enrollment.user, None)

    def test_successful_program_enrollments_existing_user(self):
        program_key = uuid4()
        curriculum_uuid = uuid4()

        post_data = [
            {
                'status': 'enrolled',
                'external_user_key': 'abc1',
                'curriculum_uuid': str(curriculum_uuid)
            }
        ]

        user = User.objects.create_user('test_user', 'test@example.com', 'password')

        url = reverse('programs_api:v1:program_enrollments', args=[program_key])

        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            with mock.patch(
                'lms.djangoapps.program_enrollments.api.v1.views.get_user_by_program_id',
                autospec=True,
                return_value=user
            ):
                response = self.client.post(url, json.dumps(post_data), content_type='application/json')

        self.assertEqual(response.status_code, 201)

        enrollment = ProgramEnrollment.objects.first()

        self.assertEqual(enrollment.external_user_key, 'abc1')
        self.assertEqual(enrollment.program_uuid, program_key)
        self.assertEqual(enrollment.status, 'enrolled')
        self.assertEqual(enrollment.curriculum_uuid, curriculum_uuid)
        self.assertEqual(enrollment.user, user)

    def test_enrollment_payload_limit(self):

        post_data = []
        for _ in range(26):
            post_data += self.student_enrollment('enrolled')

        url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            with mock.patch(
                'lms.djangoapps.program_enrollments.api.v1.views.get_user_by_program_id',
                autospec=True,
                return_value=None
            ):
                response = self.client.post(url, json.dumps(post_data), content_type='application/json')
        self.assertEqual(response.status_code, 413)

    def test_duplicate_enrollment(self):
        post_data = [
            self.student_enrollment('enrolled', '001'),
            self.student_enrollment('enrolled', '002'),
            self.student_enrollment('enrolled', '001'),
        ]

        url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            with mock.patch(
                'lms.djangoapps.program_enrollments.api.v1.views.get_user_by_program_id',
                autospec=True,
                return_value=None
            ):
                response = self.client.post(url, json.dumps(post_data), content_type='application/json')

        self.assertEqual(response.status_code, 207)
        self.assertEqual(response.data, {
            '001': 'duplicated',
            '002': 'enrolled',
        })

    def test_unprocessable_enrollment(self):
        url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])

        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            with mock.patch(
                'lms.djangoapps.program_enrollments.api.v1.views.get_user_by_program_id',
                autospec=True,
                return_value=None
            ):
                response = self.client.post(
                    url,
                    json.dumps([{'status': 'enrolled'}]),
                    content_type='application/json'
                )

        self.assertEqual(response.status_code, 422)

    def test_unauthenticated(self):
        self.client.logout()
        post_data = [
            self.student_enrollment('enrolled')
        ]
        url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        response = self.client.post(
            url,
            json.dumps(post_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 401)

    def test_program_unauthorized(self):
        student = UserFactory.create(username='student', password='password')
        self.client.login(username=student.username, password='password')

        post_data = [
            self.student_enrollment('enrolled')
        ]
        url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        response = self.client.post(
            url,
            json.dumps(post_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_program_not_found(self):
        post_data = [
            self.student_enrollment('enrolled')
        ]
        url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        response = self.client.post(
            url,
            json.dumps(post_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_partially_valid_enrollment(self):

        post_data = [
            self.student_enrollment('new', '001'),
            self.student_enrollment('pending', '003'),
        ]

        url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        with mock.patch('lms.djangoapps.program_enrollments.api.v1.views.get_programs', autospec=True):
            with mock.patch(
                'lms.djangoapps.program_enrollments.api.v1.views.get_user_by_program_id',
                autospec=True,
                return_value=None
            ):
                response = self.client.post(url, json.dumps(post_data), content_type='application/json')

        self.assertEqual(response.status_code, 207)
        self.assertEqual(response.data, {
            '001': 'invalid-status',
            '003': 'pending',
        })
