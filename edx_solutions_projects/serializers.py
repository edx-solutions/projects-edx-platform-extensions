""" Django REST Framework Serializers """

from django.contrib.auth.models import User
from edx_solutions_api_integration.groups.serializers import GroupSerializer
from edx_solutions_organizations.models import Organization
from rest_framework import serializers

from .models import (Project, Workgroup, WorkgroupPeerReview, WorkgroupReview,
                     WorkgroupSubmission, WorkgroupSubmissionReview)
from .utils import make_temporary_s3_link


class UserSerializer(serializers.HyperlinkedModelSerializer):
    """ Serializer for model interactions """

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = User
        fields = ('id', 'url', 'username', 'email')


class ExtendedUserSerializer(serializers.HyperlinkedModelSerializer):
    """ Serializer for model interactions """

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = User
        fields = ('id', 'url', 'username', 'email', 'first_name', 'last_name')


class GradeSerializer(serializers.Serializer):
    """ Serializer for model interactions """
    grade = serializers.Field()


class ProjectSerializer(serializers.HyperlinkedModelSerializer):
    """ Serializer for model interactions """
    workgroups = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Workgroup.objects.all())
    organization = serializers.PrimaryKeyRelatedField(required=False, queryset=Organization.objects.all())

    def validate(self, data):
        """
        Custom validation for projects model.
        we have to write custom validation because DRF makes
        all fields in unique together to be required. However we
        want organization as optional field.
        """
        if not data.get('course_id', None):
            raise serializers.ValidationError('course_id field is required.')
        if not data.get('content_id', None):
            raise serializers.ValidationError('content_id field is required.')
        return data

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = Project
        fields = (
            'id', 'url', 'created', 'modified', 'course_id', 'content_id',
            'organization', 'workgroups'
        )
        validators = []


class WorkgroupSubmissionSerializer(serializers.HyperlinkedModelSerializer):
    """ Serializer for model interactions """
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    workgroup = serializers.PrimaryKeyRelatedField(queryset=Workgroup.objects.all())
    reviews = serializers.PrimaryKeyRelatedField(many=True, queryset=WorkgroupReview.objects.all(), required=False)

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = WorkgroupSubmission
        fields = (
            'id', 'url', 'created', 'modified', 'document_id', 'document_url',
            'document_mime_type', 'document_filename',
            'user', 'workgroup', 'reviews'
        )

    def to_representation(self, instance):
        """
        Create a temporary S3 link in case of S3 URL
        """
        response = super().to_representation(instance)

        if 's3.amazonaws.com' in response.get('document_url'):
            try:
                file_sha1 = response['document_url'].split('/')[-2]
            except IndexError:
                return response

            file_path = "group_work/{}/{}/{}".format(
                response['workgroup'],
                file_sha1,
                response['document_filename'],
            )

            temp_s3_link = make_temporary_s3_link(file_path=file_path)

            if temp_s3_link is not None:
                response['document_url'] = temp_s3_link

        return response


class WorkgroupReviewSerializer(serializers.HyperlinkedModelSerializer):
    """ Serializer for model interactions """
    workgroup = serializers.PrimaryKeyRelatedField(queryset=Workgroup.objects.all())

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = WorkgroupReview
        fields = (
            'id', 'url', 'created', 'modified', 'question', 'answer',
            'workgroup', 'reviewer', 'content_id'
        )


class WorkgroupSubmissionReviewSerializer(serializers.HyperlinkedModelSerializer):
    """ Serializer for model interactions """
    submission = serializers.PrimaryKeyRelatedField(queryset=WorkgroupSubmission.objects.all())

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = WorkgroupSubmissionReview
        fields = (
            'id', 'url', 'created', 'modified', 'question', 'answer',
            'submission', 'reviewer', 'content_id'
        )


class WorkgroupPeerReviewSerializer(serializers.HyperlinkedModelSerializer):
    """ Serializer for model interactions """
    workgroup = serializers.PrimaryKeyRelatedField(queryset=Workgroup.objects.all())
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = WorkgroupPeerReview
        fields = (
            'id', 'url', 'created', 'modified', 'question', 'answer',
            'workgroup', 'user', 'reviewer', 'content_id'
        )


class WorkgroupSerializer(serializers.HyperlinkedModelSerializer):
    """ Serializer for model interactions """
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    groups = GroupSerializer(many=True, required=False)
    users = ExtendedUserSerializer(many=True, required=False)
    submissions = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=WorkgroupSubmission.objects.all())
    workgroup_reviews = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=WorkgroupReview.objects.all())
    peer_reviews = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=WorkgroupPeerReview.objects.all())

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = Workgroup
        fields = (
            'id', 'url', 'created', 'modified', 'name', 'project',
            'groups', 'users', 'submissions',
            'workgroup_reviews', 'peer_reviews'
        )


class OrganizationSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = Organization
        fields = ('id', 'display_name')


class UserDetailsSerializer(serializers.HyperlinkedModelSerializer):
    organizations = OrganizationSerializer(many=True, required=False)

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = User
        fields = ('id', 'url', 'username', 'email', 'first_name', 'last_name', 'organizations')


class WorkgroupDetailsSerializer(serializers.HyperlinkedModelSerializer):
    submissions = WorkgroupSubmissionSerializer(many=True, read_only=True)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    users = UserDetailsSerializer(many=True, required=False)

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = Workgroup
        fields = (
            'id', 'url', 'created', 'modified', 'name', 'project',
            'users', 'submissions',
        )


class BasicWorkgroupSerializer(serializers.HyperlinkedModelSerializer):
    """ Basic Workgroup Serializer to keep only basic fields """

    class Meta:
        """ Meta class for defining additional serializer characteristics """
        model = Workgroup
        fields = (
            'id', 'url', 'created', 'modified', 'name', 'project',
        )
