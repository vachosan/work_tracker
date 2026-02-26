from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import (
    InterventionType,
    Project,
    ProjectMembership,
    RuianCadastralArea,
    RuianCadastralAreaMunicipality,
    RuianMunicipality,
    TreeIntervention,
    WorkRecord,
)


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
        self.in_project_far = WorkRecord.objects.create(
            title="InProjectFar", latitude=49.8, longitude=17.8, vegetation_type=None
        )
        self.in_project_blank = WorkRecord.objects.create(
            title="InProjectBlank", latitude=49.7, longitude=17.7, vegetation_type=""
        )
        self.other_project = WorkRecord.objects.create(
            title="OtherProject", latitude=49.2, longitude=17.2
        )
        self.orphan = WorkRecord.objects.create(
            title="Orphan", latitude=49.3, longitude=17.3
        )
        self.project1.trees.add(self.in_project)
        self.project1.trees.add(self.in_project_far)
        self.project1.trees.add(self.in_project_blank)
        self.project2.trees.add(self.other_project)

    def test_workrecords_geojson_non_project_uses_m2m(self):
        self.client.force_login(self.user)
        url = reverse("workrecords_geojson")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        ids = {f["properties"]["id"] for f in payload.get("features", [])}
        self.assertIn(self.in_project.pk, ids)
        self.assertIn(self.in_project_far.pk, ids)
        self.assertIn(self.in_project_blank.pk, ids)
        self.assertNotIn(self.other_project.pk, ids)
        self.assertNotIn(self.orphan.pk, ids)

    def test_workrecords_geojson_project_intervention_types_ignore_bbox(self):
        type_a = InterventionType.objects.create(code="A", name="Typ A")
        type_b = InterventionType.objects.create(code="B", name="Typ B")
        TreeIntervention.objects.create(tree=self.in_project, intervention_type=type_a)
        TreeIntervention.objects.create(
            tree=self.in_project_far,
            intervention_type=type_b,
            status="completed",
        )

        self.client.force_login(self.user)
        url = reverse("workrecords_geojson")
        resp = self.client.get(
            url,
            {
                "project": self.project1.pk,
                "bbox": "17.05,49.05,17.2,49.2",
            },
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        ids = {f["properties"]["id"] for f in payload.get("features", [])}
        self.assertEqual(ids, {self.in_project.pk})
        self.assertEqual(payload.get("project_intervention_types"), ["A", "B"])
        self.assertEqual(payload.get("project_intervention_type_counts"), {"A": 1, "B": 1})
        self.assertEqual(payload.get("project_intervention_statuses"), ["proposed", "completed"])
        self.assertEqual(
            payload.get("project_intervention_status_counts"),
            {"proposed": 1, "completed": 1},
        )
        self.assertEqual(payload.get("project_vegetation_counts", {}).get("TREE"), 3)
        self.assertEqual(payload.get("project_no_intervention_count"), 1)
        feature = payload["features"][0]
        self.assertEqual(feature["properties"]["intervention_types"], ["A"])
        self.assertEqual(feature["properties"]["intervention_statuses"], ["proposed"])
        self.assertTrue(feature["properties"]["has_interventions"])


class CadastreAreaCodeDerivationTests(TestCase):
    def _create_with_parcel(self, parcel_number):
        with patch(
            "tracker.models._cad_lookup_by_point",
            return_value={"parcel_number": parcel_number, "cad_lookup_status": "ok"},
        ):
            record = WorkRecord.objects.create(
                title="WR", latitude=49.0, longitude=17.0
            )
        record.refresh_from_db()
        return record

    def test_cadastral_area_code_derived_from_parcel_number(self):
        record = self._create_with_parcel("710504-241/1")
        self.assertEqual(record.cadastral_area_code, "710504")
        record = self._create_with_parcel("713520-300/2")
        self.assertEqual(record.cadastral_area_code, "713520")

    def test_cadastral_area_code_not_set_for_invalid_parcel_number(self):
        record = self._create_with_parcel("")
        self.assertFalse(record.cadastral_area_code)
        record = self._create_with_parcel("invalid")
        self.assertFalse(record.cadastral_area_code)

    def test_cadastral_area_code_accepts_numeric_prefix(self):
        record = self._create_with_parcel("123-")
        self.assertEqual(record.cadastral_area_code, "123")


class RuianImportTests(TestCase):
    def test_import_ruian_from_sample_dir(self):
        sample_dir = Path(__file__).resolve().parent / "data" / "ruian_sample"
        call_command("import_ruian", source_dir=str(sample_dir))

        self.assertEqual(RuianMunicipality.objects.count(), 2)
        self.assertEqual(RuianCadastralArea.objects.count(), 3)
        self.assertTrue(
            RuianCadastralAreaMunicipality.objects.filter(
                cadastral_area_id="2001", municipality_id="1001"
            ).exists()
        )


class WorkRecordRuianEnrichmentTests(TestCase):
    def _create_with_parcel(self, parcel_number):
        with patch(
            "tracker.models._cad_lookup_by_point",
            return_value={"parcel_number": parcel_number, "cad_lookup_status": "ok"},
        ):
            record = WorkRecord.objects.create(
                title="WR", latitude=49.0, longitude=17.0
            )
        record.refresh_from_db()
        return record

    def test_enriches_names_from_ruian_tables(self):
        RuianCadastralArea.objects.create(code="710504", name="Katastr X")
        RuianMunicipality.objects.create(code="5001", name="Obec Y")
        RuianCadastralAreaMunicipality.objects.create(
            cadastral_area_id="710504", municipality_id="5001"
        )

        record = self._create_with_parcel("710504-241/1")
        self.assertEqual(record.cadastral_area_code, "710504")
        self.assertEqual(record.cadastral_area_name, "Katastr X")
        self.assertEqual(record.municipality_name, "Obec Y")

    def test_missing_ruian_tables_does_not_block_create(self):
        record = self._create_with_parcel("710504-241/1")
        self.assertEqual(record.cadastral_area_code, "710504")
        self.assertFalse(record.cadastral_area_name)
        self.assertFalse(record.municipality_name)
