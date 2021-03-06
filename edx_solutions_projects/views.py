# pylint: disable=C0103
# pylint: disable=W0613

""" WORKGROUPS API VIEWS """
import re

from lms.djangoapps.courseware.courses import get_course
from django.contrib.auth.models import Group, User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete, pre_delete
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from edx_solutions_api_integration.courseware_access import get_course_key
from edx_solutions_api_integration.permissions import SecureModelViewSet
from edx_solutions_projects.receivers import (delete_empty_workgroup,
                                              reassign_or_delete_submissions)
from eventtracking import tracker
from lms.djangoapps.courseware import courses
from lms.djangoapps.grades.signals.signals import SCORE_PUBLISHED
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import UsageKey
from openedx.core.djangoapps.course_groups.cohorts import (
    add_cohort, add_user_to_cohort, get_cohort_by_name,
    remove_user_from_cohort)
from openedx.core.djangoapps.course_groups.models import (CohortMembership,
                                                          CourseCohort,
                                                          CourseUserGroup)
from rest_framework import status
from rest_framework.decorators import detail_route, list_route
from rest_framework.response import Response
from student.models import CourseEnrollment, AnonymousUserId
from student.roles import CourseAccessRole, CourseAssistantRole
from xmodule.modulestore.django import modulestore

from .models import (Project, Workgroup, WorkgroupPeerReview, WorkgroupReview,
                     WorkgroupSubmission, WorkgroupSubmissionReview,
                     WorkgroupUser)
from .serializers import (GroupSerializer, ProjectSerializer, UserSerializer,
                          WorkgroupDetailsSerializer,
                          WorkgroupPeerReviewSerializer,
                          WorkgroupReviewSerializer, WorkgroupSerializer,
                          WorkgroupSubmissionReviewSerializer,
                          WorkgroupSubmissionSerializer,
                          WorkgroupSubmissionBaseSerializer)
from .utils import skip_signal


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
        if assignment_type not in list(dict(CourseCohort.ASSIGNMENT_TYPE_CHOICES).keys()):
            message = "Not a valid assignment type, '{}'".format(assignment_type)
            return Response({'details': message}, status.HTTP_400_BAD_REQUEST)
        response = super().create(request)
        if response.status_code == status.HTTP_201_CREATED:
            # create the workgroup cohort
            workgroup = get_object_or_404(self.queryset, pk=response.data['id'])
            course_key = get_course_key(workgroup.project.course_id)
            add_cohort(course_key, workgroup.cohort_name, assignment_type)

        return response

    def destroy(self, request, pk):
        """
        Delete a workgroup and its cohort.
        """
        work_group = self.get_object()
        course_key = get_course_key(work_group.project.course_id)
        cohort = get_cohort_by_name(course_key, work_group.cohort_name)
        response = super().destroy(request, pk)
        if response.status_code == status.HTTP_204_NO_CONTENT:
            cohort.delete()
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
                return Response({"detail": str(e)}, status.HTTP_400_BAD_REQUEST)

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
                if assignment_type not in list(dict(CourseCohort.ASSIGNMENT_TYPE_CHOICES).keys()):
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

    @list_route(methods=['get'])
    def last_group_id(self, request):
        project_id = request.query_params.get('project_id')

        if not project_id:
            return Response({"detail": 'project_id param is required'}, status.HTTP_400_BAD_REQUEST)

        queryset = self.queryset.filter(project_id=int(project_id))

        group_names = [group for group in queryset.values_list('name', flat=True) if re.findall(r'^Group \d+$', group)]
        last_group_id = max([int(name.split()[-1]) for name in group_names] or [0])

        return Response({'last_group_id': last_group_id})

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

        return super().list(request, *args, **kwargs)

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

    @detail_route(methods=['get'])
    def workgroup_reviews(self, request, pk):
        """
        View Workgroup Reviews for a specific Workgroup
        """
        workgroup_reviews = WorkgroupReview.objects.filter(workgroup__project=pk)
        serializer = WorkgroupReviewSerializer(workgroup_reviews, context={'request': request}, many=True)
        reviews = serializer.data
        users = dict(AnonymousUserId.objects.filter(
            anonymous_user_id__in=[w.reviewer for w in workgroup_reviews]
        ).values_list('anonymous_user_id', 'user__email'))
        groups = dict(Workgroup.objects.filter(
            id__in=[w.workgroup_id for w in workgroup_reviews]
        ).values_list('id', 'name'))
        for review in reviews:
            review['reviewer_email'] = users.get(review['reviewer'], review['reviewer'])
            review['workgroup_name'] = groups.get(review['workgroup'], review['workgroup'])
        return Response(reviews, status=status.HTTP_200_OK)

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
                workgroups = workgroups.prefetch_related('submissions', 'users', 'users__organizations')
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

    @detail_route(methods=['post'])
    def validate(self, request, pk):
        project = Project.objects.filter(pk=pk).first()
        if not project:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        course_key = get_course_key(project.course_id)

        ta_emails = request.data.get('ta_emails', [])
        ta_access_emails = CourseAccessRole.objects.filter(
            user__email__in=ta_emails,
            role=CourseAssistantRole.ROLE,
            course_id=course_key,
            org=course_key.org,
        ).values_list('user__email', flat=True)
        not_ta_access = set(ta_emails) - set(ta_access_emails)
        errors = {}
        if not_ta_access:
            errors['not_ta_access'] = list(not_ta_access)

        groups = request.data.get('groups', [])
        existing = Workgroup.objects.filter(name__in=groups, project=project).values_list('name', 'id')
        existing = dict(existing)
        non_existing_groups = set(groups) - set(existing)
        if non_existing_groups:
            errors['non_existing_groups'] = list(non_existing_groups)

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(existing, status=status.HTTP_200_OK)

    @detail_route(methods=['post'])
    @method_decorator(transaction.non_atomic_requests)
    def workgroups_bulk(self, request, pk):
        self.project = Project.objects.filter(pk=pk).first()
        if not self.project:
            return Response({}, status=status.HTTP_404_NOT_FOUND)

        existing_submissions = WorkgroupSubmission.objects.filter(
            workgroup__project=self.project
        ).values_list('workgroup__name', flat=True)
        if existing_submissions:
            return Response({'existing_submissions': existing_submissions}, status=status.HTTP_400_BAD_REQUEST)

        errors = {}
        self.course_key = get_course_key(self.project.course_id)
        self.groups = request.data.get('groups', {})

        users = sum(list(self.groups.values()), [])
        users = [u.lower() for u in users]
        enrollments = CourseEnrollment.objects.filter(
            course_id=self.course_key,
            is_active=True,
            user__email__in=users
        ).values_list('user__id', 'user__email')

        self.enrolled_users = {u.lower(): i for i, u in enrollments}
        not_enrolled_users = set(users) - set(self.enrolled_users)
        if not_enrolled_users:
            errors['not_enrolled_users'] = list(not_enrolled_users)

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        self.user_ids = list(self.enrolled_users.values())

        # Delete and recreate workgroups
        self._delete_groups()
        self._create_new_workgroups()

        # Delete and recreate cohort groups and memberships
        workgroups = self._get_workgroups()
        memberships, user_group = self._get_course_membership_and_groups(workgroups)
        self._delete_cohort_groups_and_users(memberships)
        self._create_cohort_groups_and_memberships(workgroups, user_group, memberships)
        return Response({}, status=status.HTTP_201_CREATED)

    def _create_new_workgroups(self):
        workgroups = self._get_workgroups()
        # Create workgroups that are not already in DB.
        new_workgroups = []
        for group in self.groups:
            if group not in workgroups:
                new_workgroups += [Workgroup(name=group, project=self.project)]

        if new_workgroups:
            Workgroup.objects.bulk_create(new_workgroups)

        all_workgroups = self._get_workgroups()
        self._add_workgroups_to_cohorts(all_workgroups, workgroups)

    def _create_cohort_groups_and_memberships(self, workgroups, user_group, memberships):
        GroupUserModel = CourseUserGroup.users.through._meta.model
        new_workgroup_users = []
        new_cohort_memberships = []
        new_cohort_group_users = []
        for group, users in self.groups.items():
            for email in users:
                user_id = self.enrolled_users[email.lower()]
                wg = workgroups[group]
                workgroup_id = wg['id']
                cohort_name = wg['cohort_name']
                user_group_id = user_group[cohort_name]
                new_workgroup_users += [WorkgroupUser(workgroup_id=workgroup_id, user_id=user_id)]
                new_cohort_memberships += [CohortMembership(
                    course_user_group_id=user_group_id,
                    user_id=user_id,
                    course_id=self.course_key
                )]
                new_cohort_group_users += [GroupUserModel(courseusergroup_id=user_group_id, user_id=user_id)]

                membership = memberships.get(user_id, {})
                tracker.emit(
                    "edx.cohort.user_add_requested",
                    {
                        "user_id": user_id,
                        "cohort_id": user_group_id,
                        "cohort_name": cohort_name,
                        "previous_cohort_id": membership.get('id'),
                        "previous_cohort_name": membership.get('name'),
                    }
                )

        if new_workgroup_users:
            WorkgroupUser.objects.bulk_create(new_workgroup_users)
        if new_cohort_memberships:
            CohortMembership.objects.bulk_create(new_cohort_memberships)
        if new_cohort_group_users:
            GroupUserModel.objects.bulk_create(new_cohort_group_users)

    def _add_workgroups_to_cohorts(self, all_workgroups, workgroups):
        course = courses.get_course_by_id(self.course_key)
        course_id = course.id
        cohorts = [w['cohort_name'] for w in all_workgroups.values()if w['name'] not in workgroups]
        objects = []
        for cohort_name in cohorts:
            cug = CourseUserGroup(name=cohort_name, course_id=course_id, group_type=CourseUserGroup.COHORT)
            objects += [cug]
        if objects:
            CourseUserGroup.objects.bulk_create(objects)

        user_groups = CourseUserGroup.objects.filter(
            name__in=cohorts,
            course_id=course_id,
            group_type=CourseUserGroup.COHORT
        ).values_list('name', 'id')
        user_groups = dict(user_groups)

        objects = []
        for cohort_name in cohorts:
            course_user_group = user_groups[cohort_name]
            cc = CourseCohort(course_user_group_id=course_user_group, assignment_type=CourseCohort.RANDOM)
            objects += [cc]

        if objects:
            CourseCohort.objects.bulk_create(objects)

    def _get_workgroups(self):
        raw_workgroups = Workgroup.objects.filter(
            name__in=list(self.groups),
            project=self.project
        ).values('id', 'project_id', 'name')

        workgroups = {}
        for workgroup in raw_workgroups:
            project_id = workgroup['project_id']
            workgroup_id = workgroup['id']
            workgroup_name = workgroup['name']
            workgroup['cohort_name'] = Workgroup.cohort_name_for_workgroup(
                project_id, workgroup_id, workgroup_name
            )
            workgroups[workgroup_name] = workgroup

        return workgroups

    def _get_course_membership_and_groups(self, workgroups):
        user_groups = CourseUserGroup.objects.filter(
            course_id=self.course_key,
            group_type=CourseUserGroup.COHORT,
            name__in=[w['cohort_name'] for w in workgroups.values()]
        ).values_list('id', 'name')
        user_group = {n: i for i, n in user_groups}

        memberships = CohortMembership.objects.filter(
            course_id=self.course_key,
            user_id__in=self.user_ids
        ).values_list(
            'user_id',
            'course_user_group_id',
            'course_user_group__name'
        )
        memberships = {u: {'id': m, 'name': n} for u, m, n in memberships}
        return memberships, user_group

    def _delete_groups(self):
        with skip_signal(pre_delete, receiver=reassign_or_delete_submissions, sender=WorkgroupUser):
            with skip_signal(post_delete, receiver=delete_empty_workgroup, sender=WorkgroupUser):
                Workgroup.objects.filter(name__in=list(self.groups), project=self.project).delete()

        WorkgroupUser.objects.filter(
            user__in=list(self.enrolled_users.values()),
            workgroup__project__course_id=self.course_key
        ).delete()

    def _delete_cohort_groups_and_users(self, memberships):
        GroupUserModel = CourseUserGroup.users.through._meta.model
        q = Q()
        for user_id, group in memberships.items():
            q |= Q(courseusergroup_id=group['id'], user_id=user_id)
        GroupUserModel.objects.filter(q).delete()
        from openedx.core.djangoapps.course_groups.models import remove_user_from_cohort as ch_signal
        with skip_signal(pre_delete, receiver=ch_signal, sender=CohortMembership):
            CohortMembership.objects.filter(
                course_id=self.course_key,
                user_id__in=self.user_ids
            ).delete()


class WorkgroupSubmissionsViewSet(SecureModelViewSet):
    """
    Django Rest Framework ViewSet for the Submission model.
    """
    serializer_class = WorkgroupSubmissionSerializer
    queryset = WorkgroupSubmission.objects.all()

    @list_route(methods=['post'])
    def by_workgroups_and_users(self, request):
        """
        View Submissions submitted by specific Workgroups and Users
        """
        user_ids = request.data.get('user_ids')
        workgroup_ids = request.data.get('workgroup_ids')
        submissions = self.queryset

        if workgroup_ids:
            submissions = self.queryset.filter(workgroup__in=workgroup_ids)

        if user_ids:
            submissions = submissions.filter(user__in=user_ids)

        response_data = []
        for submission in submissions:
            serializer = WorkgroupSubmissionBaseSerializer(submission, context={'request': request})
            response_data.append(serializer.data)  # pylint: disable=E1101

        return Response(response_data, status=status.HTTP_200_OK)


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
