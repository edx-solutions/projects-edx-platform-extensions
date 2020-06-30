# pylint: disable=C0103
# pylint: disable=W0613

""" WORKGROUPS API VIEWS """
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.utils.decorators import method_decorator
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from rest_framework.decorators import detail_route
from rest_framework import status
from rest_framework.response import Response

from lms.djangoapps.grades.signals.signals import SCORE_PUBLISHED
from openedx.core.djangoapps.course_groups.models import CourseCohort

from edx_solutions_api_integration.permissions import SecureModelViewSet
from edx_solutions_api_integration.courseware_access import get_course_key
from courseware.courses import get_course
from opaque_keys.edx.keys import CourseKey, UsageKey
from opaque_keys import InvalidKeyError
from xmodule.modulestore.django import modulestore
from openedx.core.djangoapps.course_groups.cohorts import (
    add_cohort, add_user_to_cohort, get_cohort_by_name, remove_user_from_cohort,
)

from .models import Project, Workgroup, WorkgroupSubmission
from .models import WorkgroupReview, WorkgroupSubmissionReview, WorkgroupPeerReview
from .serializers import UserSerializer, GroupSerializer, WorkgroupDetailsSerializer
from .serializers import ProjectSerializer, WorkgroupSerializer, WorkgroupSubmissionSerializer
from .serializers import WorkgroupReviewSerializer, WorkgroupSubmissionReviewSerializer, WorkgroupPeerReviewSerializer


class GroupViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the Group model (auth_group).
    """
    serializer_class = GroupSerializer
    queryset = Group.objects.all()


class UserViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the User model (auth_user).
    """
    serializer_class = UserSerializer
    queryset = User.objects.all()


class WorkgroupsViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the Workgroup model.
    """
    serializer_class = WorkgroupSerializer
    queryset = Workgroup.objects.prefetch_related(
        "submissions", "workgroup_reviews", "peer_reviews",
        "groups", "users", "groups__groupprofile"
    ).all()

    def create(self, request):
        """
        Create a new workgroup and its cohort.
        """
        assignment_type = request.data.get('assignment_type', CourseCohort.RANDOM)
        if assignment_type not in dict(CourseCohort.ASSIGNMENT_TYPE_CHOICES).keys():
            message = "Not a valid assignment type, '{}'".format(assignment_type)
            return Response({'details': message}, status.HTTP_400_BAD_REQUEST)
        response = super(WorkgroupsViewSet, self).create(request)
        if response.status_code == status.HTTP_201_CREATED:
            # create the workgroup cohort
            workgroup = get_object_or_404(self.queryset, pk=response.data['id'])
            course_key = get_course_key(workgroup.project.course_id)
            add_cohort(course_key, workgroup.cohort_name, assignment_type)

        return response

    @detail_route(methods=['get', 'post'])
    def groups(self, request, pk):
        """
        Add a Group to a Workgroup
        """
        if request.method == 'GET':
            groups = Group.objects.filter(workgroups=pk)
            response_data = []
            if groups:
                for group in groups:
                    serializer = GroupSerializer(group, context={'request': request})
                    response_data.append(serializer.data)  # pylint: disable=E1101
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            group_id = request.data.get('id')
            try:
                group = Group.objects.get(id=group_id)
            except ObjectDoesNotExist:
                message = 'Group {} does not exist'.format(group_id)
                return Response({"detail": message}, status.HTTP_400_BAD_REQUEST)
            workgroup = self.get_object()
            workgroup.groups.add(group)
            workgroup.save()
            return Response({}, status=status.HTTP_201_CREATED)

    @detail_route(methods=['get', 'post', 'delete'])
    @method_decorator(transaction.non_atomic_requests)
    def users(self, request, pk):
        """
        Add a User to a Workgroup
        """
        if request.method == 'GET':
            users = User.objects.filter(workgroups=pk)
            response_data = []
            if users:
                for user in users:
                    serializer = UserSerializer(user, context={'request': request})
                    response_data.append(serializer.data)  # pylint: disable=E1101
            return Response(response_data, status=status.HTTP_200_OK)
        elif request.method == 'POST':
            user_id = request.data.get('id')
            try:
                user = User.objects.get(id=user_id)
            except ObjectDoesNotExist:
                message = 'User {} does not exist'.format(user_id)
                return Response({"detail": message}, status.HTTP_400_BAD_REQUEST)

            workgroup = self.get_object()

            # Ensure the user is not already assigned to a project for this course
            existing_projects = Project.objects.filter(course_id=workgroup.project.course_id).filter(workgroups__users__id=user.id)
            if len(existing_projects):
                message = 'User {} already assigned to a project for this course'.format(user_id)
                return Response({"detail": message}, status.HTTP_400_BAD_REQUEST)

            try:
                workgroup.add_user(user)
            except ValidationError as e:
                return Response({"detail": unicode(e)}, status.HTTP_400_BAD_REQUEST)

            workgroup.save()

            # add user to the workgroup cohort, create it if it doesn't exist (for cases where there is a legacy
            # workgroup)
            course_key = get_course_key(workgroup.project.course_id)
            try:
                cohort = get_cohort_by_name(course_key, workgroup.cohort_name)
                add_user_to_cohort(cohort, user.username)
            except ObjectDoesNotExist:
                # This use case handles cases where a workgroup might have been created before
                # the notion of a cohorted discussion. So we need to backfill in the data
                assignment_type = request.data.get('assignment_type', CourseCohort.RANDOM)
                if assignment_type not in dict(CourseCohort.ASSIGNMENT_TYPE_CHOICES).keys():
                    message = "Not a valid assignment type, '{}'".format(assignment_type)
                    return Response({"detail": message}, status.HTTP_400_BAD_REQUEST)
                workgroup = self.get_object()
                cohort = add_cohort(course_key, workgroup.cohort_name, assignment_type)
                for workgroup_user in workgroup.users.all():
                    add_user_to_cohort(cohort, workgroup_user.username)
            return Response({}, status=status.HTTP_201_CREATED)
        else:
            user_id = request.data.get('id')
            try:
                user = User.objects.get(id=user_id)
            except ObjectDoesNotExist:
                message = 'User {} does not exist'.format(user_id)
                return Response({"detail": message}, status.HTTP_400_BAD_REQUEST)
            workgroup = self.get_object()
            course_key = get_course_key(workgroup.project.course_id)
            cohort = get_cohort_by_name(course_key, workgroup.cohort_name)
            workgroup.remove_user(user)
            remove_user_from_cohort(cohort, user.username)
            return Response({}, status=status.HTTP_204_NO_CONTENT)

    @detail_route(methods=['get'])
    def peer_reviews(self, request, pk):
        """
        View Peer Reviews for a specific Workgroup
        """
        peer_reviews = WorkgroupPeerReview.objects.filter(workgroup=pk)
        content_id = self.request.query_params.get('content_id', None)
        if content_id is not None:
            peer_reviews = peer_reviews.filter(content_id=content_id)
        response_data = []
        if peer_reviews:
            for peer_review in peer_reviews:
                serializer = WorkgroupPeerReviewSerializer(peer_review, context={'request': request})
                response_data.append(serializer.data)  # pylint: disable=E1101
        return Response(response_data, status=status.HTTP_200_OK)

    @detail_route(methods=['get'])
    def workgroup_reviews(self, request, pk):
        """
        View Workgroup Reviews for a specific Workgroup
        """
        workgroup_reviews = WorkgroupReview.objects.filter(workgroup=pk)
        content_id = self.request.query_params.get('content_id', None)
        if content_id is not None:
            workgroup_reviews = workgroup_reviews.filter(content_id=content_id)

        response_data = []
        if workgroup_reviews:
            for workgroup_review in workgroup_reviews:
                serializer = WorkgroupReviewSerializer(workgroup_review, context={'request': request})
                response_data.append(serializer.data)  # pylint: disable=E1101
        return Response(response_data, status=status.HTTP_200_OK)

    @detail_route(methods=['get'])
    def score(self, request, pk):
        """
        View final score for a specific Workgroup
        """
        block_id = self.request.query_params.get('block_id', None)
        if not block_id:
            message = 'Query string for "block_id" is required.'
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)
        child_key = UsageKey.from_string(block_id)
        if child_key.category != 'gp-v2-activity':
            message = 'The "block_id" should point to a "gp-v2-activity" block.'
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)
        descriptor = modulestore().get_item(child_key)
        score = descriptor.calculate_grade(group_id=pk)
        return Response({'score': score}, status=status.HTTP_200_OK)

    @detail_route(methods=['get'])
    def submissions(self, request, pk):
        """
        View Submissions for a specific Workgroup
        """
        submissions = WorkgroupSubmission.objects.filter(workgroup=pk)
        response_data = []
        if submissions:
            for submission in submissions:
                serializer = WorkgroupSubmissionSerializer(submission, context={'request': request})
                response_data.append(serializer.data)  # pylint: disable=E1101
        return Response(response_data, status=status.HTTP_200_OK)

    @detail_route(methods=['post'])
    def grades(self, request, pk):
        """
        Submit a grade for a Workgroup.  The grade will be applied to all members of the workgroup
        """
        # Ensure we received all of the necessary information
        course_id = request.data.get('course_id')
        if course_id is None:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

        course_key = get_course_key(course_id)
        if not course_key:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

        course_descriptor = get_course(course_key)
        if not course_descriptor:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

        content_id = request.data.get('content_id')
        if content_id is None:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usage_key = UsageKey.from_string(content_id)
        except InvalidKeyError:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)
        content_descriptor = modulestore().get_item(usage_key)
        if content_descriptor is None:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

        grade = request.data.get('grade')
        if grade is None:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

        max_grade = request.data.get('max_grade')
        if max_grade is None:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)
        if grade > max_grade:
            max_grade = grade

        users = User.objects.filter(workgroups=pk)
        for user in users:
            SCORE_PUBLISHED.send(
                sender=None,
                block=content_descriptor,
                user=user,
                raw_earned=grade,
                raw_possible=max_grade,
                only_if_higher=None,
                )

        return Response({}, status=status.HTTP_201_CREATED)


class ProjectsViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the Project model.
    """
    serializer_class = ProjectSerializer
    queryset = Project.objects.prefetch_related("workgroups").all()

    def list(self, request, *args, **kwargs):
        """
        GET /api/projects/
        Returns list of projects, optionally filtered by course ID and content ID (simultaneously)
        """
        target_course_id = self.request.query_params.get('course_id')
        target_content_id = self.request.query_params.get('content_id')
        has_target_course, has_target_content = bool(target_course_id), bool(target_content_id)

        if has_target_course != has_target_content:
            message = "Both course_id and content_id should be present for filtering"
            return Response({"detail": message}, status.HTTP_400_BAD_REQUEST)

        return super(ProjectsViewSet, self).list(request, *args, **kwargs)

    def get_queryset(self):
        """
        Returns queryset optionally filtered by course_id and content_id
        """
        target_course_id = self.request.query_params.get('course_id')
        target_content_id = self.request.query_params.get('content_id')

        queryset = self.queryset

        if target_content_id:
            queryset = queryset.filter(content_id=target_content_id, course_id=target_course_id)

        return queryset

    @detail_route(methods=['get', 'post'])
    def workgroups(self, request, pk):
        """
        Add a Workgroup to a Project
        """
        if request.method == 'GET':
            workgroups = Workgroup.objects.filter(project=pk)
            serializer_cls = WorkgroupSerializer
            if 'details' in request.query_params:
                serializer_cls = WorkgroupDetailsSerializer
                workgroups = workgroups.prefetch_related('submissions')
            response_data = []
            if workgroups:
                for workgroup in workgroups:
                    serializer = serializer_cls(workgroup, context={'request': request})
                    response_data.append(serializer.data)  # pylint: disable=E1101
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            workgroup_id = request.data.get('id')
            try:
                workgroup = Workgroup.objects.get(id=workgroup_id)
            except ObjectDoesNotExist:
                message = 'Workgroup {} does not exist'.format(workgroup_id)
                return Response({"detail": message}, status.HTTP_400_BAD_REQUEST)
            project = self.get_object()
            project.workgroups.add(workgroup)
            project.save()
            return Response({}, status=status.HTTP_201_CREATED)


class WorkgroupSubmissionsViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the Submission model.
    """
    serializer_class = WorkgroupSubmissionSerializer
    queryset = WorkgroupSubmission.objects.all()


class WorkgroupReviewsViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the ProjectReview model.
    """
    serializer_class = WorkgroupReviewSerializer
    queryset = WorkgroupReview.objects.all()


class WorkgroupSubmissionReviewsViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the SubmissionReview model.
    """
    serializer_class = WorkgroupSubmissionReviewSerializer
    queryset = WorkgroupSubmissionReview.objects.all()


class WorkgroupPeerReviewsViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the PeerReview model.
    """
    serializer_class = WorkgroupPeerReviewSerializer
    queryset = WorkgroupPeerReview.objects.all()
