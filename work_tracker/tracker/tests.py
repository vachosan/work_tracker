from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Project, ProjectMembership, WorkRecord


class ProjectTreeAddTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="worker", password="pass1234"
        )
        self.foreman = get_user_model().objects.create_user(
            username="foreman", password="pass1234"
        )
        self.project = Project.objects.create(name="P1")
        ProjectMembership.objects.create(
            user=self.user, project=self.project, role=ProjectMembership.Role.WORKER
        )
        ProjectMembership.objects.create(
            user=self.foreman,
            project=self.project,
            role=ProjectMembership.Role.FOREMAN,
        )
        self.work_record = WorkRecord.objects.create(
            title="WR-1", latitude=49.0, longitude=17.0
        )

    def test_project_tree_add_requires_foreman(self):
        self.client.force_login(self.user)
        url = reverse("project_tree_add", args=[self.project.pk, self.work_record.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)

    def test_project_tree_add_sets_fk_if_null(self):
        self.client.force_login(self.foreman)
        url = reverse("project_tree_add", args=[self.project.pk, self.work_record.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.work_record.refresh_from_db()
        self.assertTrue(self.project.trees.filter(pk=self.work_record.pk).exists())
        self.assertEqual(self.work_record.project_id, self.project.pk)


class WorkrecordsGeojsonTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="user1", password="pass1234"
        )
        self.project1 = Project.objects.create(name="P1")
        self.project2 = Project.objects.create(name="P2")
        ProjectMembership.objects.create(
            user=self.user,
            project=self.project1,
            role=ProjectMembership.Role.WORKER,
        )
        self.in_project = WorkRecord.objects.create(
            title="InProject", latitude=49.1, longitude=17.1
        )
        self.other_project = WorkRecord.objects.create(
            title="OtherProject", latitude=49.2, longitude=17.2
        )
        self.orphan = WorkRecord.objects.create(
            title="Orphan", latitude=49.3, longitude=17.3
        )
        self.project1.trees.add(self.in_project)
        self.project2.trees.add(self.other_project)

    def test_workrecords_geojson_non_project_uses_m2m(self):
        self.client.force_login(self.user)
        url = reverse("workrecords_geojson")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        ids = {f["properties"]["id"] for f in payload.get("features", [])}
        self.assertIn(self.in_project.pk, ids)
        self.assertNotIn(self.other_project.pk, ids)
        self.assertNotIn(self.orphan.pk, ids)
