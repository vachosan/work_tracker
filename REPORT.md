# Souhrn změn
- Nově je `Project` připraven na M2M skrz `ProjectTree`, takže jednoho stromu se může dotýkat víc projektů a každý má ještě dál legacy FK `project` pro backward-compatibilitu (`work_tracker/tracker/models.py:65-408`).
- Přidány modely `Dataset`/`DatasetTree`/`ProjectTree`, adminy i helper `tracker/datasets.py`, aby existoval vždy systémový dataset „Veřejná stromová mapa“ a strom lze přidat do datasetů s odpovídajícími indexy a Omezením (`work_tracker/tracker/models.py:328-409`, `work_tracker/tracker/admin.py`, `work_tracker/tracker/datasets.py`).
- Migrace `0023_...` vytvořila nové tabulky/ManyToMany, `0024_populate_system_dataset` vložila stávající WorkRecordy do systémového datasetu a vytvořila vazby mezi legacy `project` a novým `ProjectTree` (`work_tracker/tracker/migrations/0023_*.py`, `work_tracker/tracker/migrations/0024_populate_system_dataset.py`).
- Signál `post_save(WorkRecord)` zajišťuje automatické vkládání nových stromů do systémového datasetu přes `get_system_dataset()`; kód vše ignoruje přerušené přidání, aby neblokoval tvorbu stromu (`work_tracker/tracker/models.py` + `tracker/datasets.py` helper).

# Migrace a datová synchronizace
- Schema migrace přidala `Dataset`, `DatasetTree`, `ProjectTree`, indexy a `Project.trees` M2M. Všechna omezení (unique pro systémový dataset, unique_together a indexy) jsou definována přímo v migraci.
- Datová migrace `0024`:
  - vytvoří (nebo najde) systémový dataset
  - vloží každý existující WorkRecord do `DatasetTree`
  - pro každý `WorkRecord.project_id` doplní `ProjectTree`
  - používá `bulk_create(..., ignore_conflicts=True)` pro nízký dopad na DB

# Automatické přidání stromu do systémového datasetu
- `post_save` signál u `WorkRecord` (zavoláno jen při `created`) načte systémový dataset přes `get_system_dataset()` v `tracker/datasets.py` a uloží `DatasetTree` záznam (`work_tracker/tracker/models.py`).
- Signál je idempotentní, `DatasetTree.objects.get_or_create` nehodí chybu, a výjimky se potlačí, aby `WorkRecord` vznikl i kdyby dataset chyběl.

# Další kroky v UI/architektuře
- Refaktor mapového kontextu a všech `project` filtrů na použití `ProjectTree`+datasetů (neměnit ještě JS, ale přechod požaduje novou M2M logiku).
- Přidat uživatelské rozhraní „přidat strom do projektu“ a možnost spravovat dataset membership (zatím pouze datová základna).
- Implementovat crowdsourcované pozorování („TreeObservation“/inbox) až po dokončení přechodu na nové datasety.

# Fáze „ProjectTree“ – přechod backendu
- `project_detail` nyní vytváří základní queryset přes `project.trees` (všechny stromové zápisy svázané M2M) a následně aplikuje stejné filtry/prefetch jako dříve; starý `WorkRecord.objects.filter(project=project)` se nahrazuje v `work_tracker/tracker/views.py:81-132`.
- `export_selected_zip` z větví `export_all_requested` i výběru stromů přechází na `project.trees` (`work_tracker/tracker/views.py:681-720`), takže ZIP export zahrnuje přesně ty stromy, které mají M2M vazbu, nikoli jen legacy FK.
- Akce nad záznamy (`bulk_approve_interventions`, `bulk_handover_interventions`, `bulk_complete_interventions`) filtrují `project.trees.filter(id__in=selected_ids)`, aby se zásahy vybíraly podle nové M2M logiky (`work_tracker/tracker/views.py:801-1471`).
