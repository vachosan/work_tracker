;(function () {
  'use strict';

  const cfg = {
    workRecordDetailApiBase: null,
    assessmentApiBase: null,
    mapUploadPhotoUrl: null,
    csrfToken: null,
    interventionNoteData: {},
  };

  const recordCache = {};
  let currentWorkRecordId = null;

  let bottomPanel;
  let treePanel;
  let backLink;
  let backLinkDefaultHref;

  let photoViewer;
  let photoViewerImg;
  let photoViewerPrev;
  let photoViewerNext;
  let photoViewerClose;
  let currentAlbum = [];
  let currentPhotoIndex = 0;

  let photoCaptureInput;
  let photoCaptureModal;
  let capturePreview;
  let captureCommentInput;
  let captureCommentToggle;
  let captureCommentWrap;
  let captureSaveBtn;
  let captureCancelBtn;
  let captureFile = null;
  let captureRecordId = null;

  let assessmentModal;
  let assessmentWorkRecordIdInput;
  let assessmentDbhInput;
  let assessmentHeightInput;
  let assessmentPhysAge;
  let assessmentVitality;
  let assessmentHealth;
  let assessmentStability;
  let assessmentPhysAgeValue;
  let assessmentVitalityValue;
  let assessmentHealthValue;
  let assessmentStabilityValue;
  let assessmentPerspectiveSlider;
  let assessmentPerspectiveValue;
  let assessmentSaveBtn;
  let assessmentCancelBtn;
  let assessmentCloseBtn;
  let assessmentMessage;

  let interventionModal;
  let interventionForm;
  let interventionTreeIdInput;
  let interventionCloseBtn;
  let interventionCancelBtn;
  let interventionSaveBtn;
  let interventionApiTemplate = '';
  let interventionNoteHintModal;
  let interventionFormErrors;
  let interventionTypeSelect;
  let interventionListContainer;

  function mergeConfig() {
    const userCfg = window.workTrackerMapUiConfig || {};
    if (!userCfg || typeof userCfg !== 'object') return;
    if (userCfg.workRecordDetailApiBase) {
      cfg.workRecordDetailApiBase = userCfg.workRecordDetailApiBase;
    }
    if (userCfg.assessmentApiBase) {
      cfg.assessmentApiBase = userCfg.assessmentApiBase;
    }
    if (userCfg.mapUploadPhotoUrl) {
      cfg.mapUploadPhotoUrl = userCfg.mapUploadPhotoUrl;
    }
    if (userCfg.csrfToken) {
      cfg.csrfToken = userCfg.csrfToken;
    }
    if (userCfg.interventionNoteData) {
      cfg.interventionNoteData = userCfg.interventionNoteData || {};
    }
  }

  function openBottomPanel() {
    if (bottomPanel) bottomPanel.classList.add('open');
  }

  function closeBottomPanel() {
    if (bottomPanel) bottomPanel.classList.remove('open');
  }

  function closeTreePanel() {
    if (!treePanel) return;
    treePanel.innerHTML = '';
    closeBottomPanel();
    currentWorkRecordId = null;
    window.activeRecordId = null;
  }

  function updateBackLink(recordId) {
    if (!backLink) return;
    if (recordId) {
      backLink.href = '/tracker/' + recordId + '/';
    } else if (backLinkDefaultHref) {
      backLink.href = backLinkDefaultHref;
    }
  }

  function getRecordDisplayLabel(record) {
    if (!record) return '';
    if (record.title && String(record.title).trim()) {
      return String(record.title).trim();
    }
    return String(record.id);
  }

  function buildPhotosHtml(record, state) {
    if ((state && state.loadingPhotos) || record.photosLoading) {
      return '<div class="text-muted small mt-2 mb-0">Načítám fotografie…</div>';
    }
    if (state && state.errorMessage) {
      return '<div class="text-danger small mt-2 mb-0">' + state.errorMessage + '</div>';
    }
    if (Array.isArray(record.photos) && record.photos.length) {
      const photosForDisplay = record.photos.slice(0, 2);
      return (
        '<div class="wr-photos">' +
        photosForDisplay
          .map(function (photo, idx) {
            const thumb = photo.thumb || photo.full || '';
            const full = photo.full || thumb;
            return (
              '<img class="wr-photo-thumb" src="' +
              thumb +
              '" alt="Foto ' +
              getRecordDisplayLabel(record) +
              '" loading="lazy" data-full="' +
              full +
              '" data-record-id="' +
              record.id +
              '" data-photo-index="' +
              idx +
              '">'
            );
          })
          .join('') +
        '</div>'
      );
    }
    if (record.has_photos) {
      return '<div class="text-muted small mt-2 mb-0">Fotky se načtou po kliknutí na bod.</div>';
    }
    return '<div class="text-muted small mt-2 mb-0">Bez fotodokumentace</div>';
  }

  function buildPopupHtml(record, state) {
    const detailUrl = '/tracker/' + record.id + '/';
    const displayLabel = getRecordDisplayLabel(record);
    const taxon = record.taxon || '';
    const taxonHtml = taxon.trim()
      ? '<div class="wr-desc"><small class="text-muted">Taxon: ' +
        taxon.trim() +
        '</small></div>'
      : '';
    const assessClass = record.has_assessment
      ? 'wr-popup-btn assess has-assessment'
      : 'wr-popup-btn assess';

    return (
      '<div class="wr-popup">' +
      '<div><a href="' +
      detailUrl +
      '" class="wr-title">' +
      displayLabel +
      '</a></div>' +
      taxonHtml +
      buildPhotosHtml(record, state) +
      '<div class="wr-popup-actions">' +
      '<button type="button" class="wr-popup-btn photo" data-action="capture" data-record-id="' +
      record.id +
      '" title="Vyfotit"><i class="bi bi-camera-fill"></i></button>' +
      '<button type="button" class="' +
      assessClass +
      '" data-action="assessment" data-record-id="' +
      record.id +
      '" title="Hodnocení stromu"><i class="bi bi-clipboard2-pulse"></i></button>' +
      '<button type="button" class="wr-popup-btn intervention" data-action="intervention" data-record-id="' +
      record.id +
      '" title="Zásahy"><i class="bi bi-tools"></i></button>' +
      '<a class="wr-popup-btn edit" href="/tracker/' +
      record.id +
      '/edit/" title="Upravit úkon"><i class="bi bi-pencil-square"></i></a>' +
      '</div>' +
      '</div>'
    );
  }

  function renderTreePanel(record, state) {
    if (!treePanel || !record) return;
    if (currentWorkRecordId !== Number(record.id)) return;
    const html =
      '<div class="tree-panel-inner">' +
      '<div class="tree-panel-header">' +
      '<span class="tree-panel-title">' +
      getRecordDisplayLabel(record) +
      '</span>' +
      '<button type="button" class="tree-panel-close" aria-label="Zavřít detail stromu">&times;</button>' +
      '</div>' +
      buildPopupHtml(record, state || {}) +
      '</div>';
    treePanel.innerHTML = html;
    openBottomPanel();
    attachPanelActionHandlers(record);
  }

  function showPanelLoading(recordId) {
    if (!treePanel) return;
    const placeholder = { id: recordId, title: 'Načítám…', has_assessment: false, has_photos: false };
    renderTreePanel(placeholder, {});
  }

  function showPanelError(recordId, message) {
    if (!treePanel) return;
    const existing = recordCache[Number(recordId)];
    const title = existing && existing.title ? existing.title : 'Detail stromu';
    const placeholder = {
      id: recordId,
      title: title,
      taxon: existing && existing.taxon ? existing.taxon : '',
      has_assessment: existing && existing.has_assessment,
      has_photos: existing && existing.has_photos,
      photos: existing && existing.photos ? existing.photos : [],
    };
    renderTreePanel(placeholder, { errorMessage: message || 'Nepodařilo se načíst detaily.' });
  }

  function attachPanelActionHandlers(record) {
    if (!treePanel) return;
    treePanel.querySelectorAll('.wr-popup-btn[data-action="capture"]').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        triggerPhotoCapture(record.id);
      });
    });
    treePanel.querySelectorAll('.wr-popup-btn[data-action="assessment"]').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openAssessmentForRecord(record.id);
      });
    });
    treePanel.querySelectorAll('.wr-popup-btn[data-action="intervention"]').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openInterventionModal(record.id);
      });
    });
  }

  function cacheRecord(record) {
    if (!record || record.id === undefined || record.id === null) return;
    recordCache[Number(record.id)] = record;
  }

  function setCurrentWorkRecord(recordId) {
    currentWorkRecordId = Number(recordId);
    window.activeRecordId = currentWorkRecordId;
    if (assessmentWorkRecordIdInput) {
      assessmentWorkRecordIdInput.value = currentWorkRecordId;
    }
    if (interventionTreeIdInput) {
      interventionTreeIdInput.value = currentWorkRecordId;
    }
  }

  function fetchRecordDetail(recordId) {
    if (!cfg.workRecordDetailApiBase) {
      return Promise.reject(new Error('Chybí konfigurace detail API.'));
    }
    const existing = recordCache[Number(recordId)];
    if (existing) {
      existing.photosLoading = true;
      cacheRecord(existing);
      renderTreePanel(existing, { loadingPhotos: true });
    }
    const url = String(cfg.workRecordDetailApiBase).replace(/\/?$/, '/') + recordId + '/';
    return fetch(url, {
      method: 'GET',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    }).then(function (resp) {
      return resp.json().then(function (body) {
        if (!resp.ok || !body || body.status !== 'ok' || !body.record) {
          const msg = (body && body.msg) || 'Nepodařilo se načíst detaily.';
          throw new Error(msg);
        }
        return body.record;
      });
    });
  }

  function openWorkRecordPanel(recordId, opts) {
    if (!recordId) return;
    const idNum = Number(recordId);
    if (!Number.isFinite(idNum)) return;
    const prefill = opts || {};

    setCurrentWorkRecord(idNum);
    updateBackLink(idNum);

    let baseRecord = recordCache[idNum];
    if (!baseRecord) {
      baseRecord = {
        id: idNum,
        title: prefill.label || 'WR ' + idNum,
        taxon: prefill.taxon || '',
        has_assessment: false,
        has_photos: false,
      };
      cacheRecord(baseRecord);
    } else if (prefill.label && (!baseRecord.title || baseRecord.title === 'Načítám…')) {
      baseRecord = { ...baseRecord, title: prefill.label };
      cacheRecord(baseRecord);
    }

    console.debug('openWorkRecordPanel prefill', { id: idNum, label: prefill.label });
    const loadingState = (!baseRecord.photos || !baseRecord.photos.length)
      ? { loadingPhotos: true }
      : {};
    renderTreePanel(baseRecord, loadingState);

    fetchRecordDetail(idNum)
      .then(function (record) {
        const existing = recordCache[idNum] || {};
        const merged = {
          ...existing,
          ...record,
          photosLoading: false,
        };
        if (prefill.label && (!record.title || !record.title.trim())) {
          merged.title = prefill.label;
        }
        cacheRecord(merged);
        renderTreePanel(merged, {});
        console.debug('detail loaded', { id: idNum });
      })
      .catch(function (err) {
        const cached = recordCache[idNum];
        if (cached) {
          cached.photosLoading = false;
          cacheRecord(cached);
        }
        showPanelError(idNum, err && err.message ? err.message : null);
      });
  }

  // ----- Photo viewer & capture -----

  function openPhotoViewer(recordId, index) {
    if (!photoViewer || !photoViewerImg) return;
    const record = recordCache[Number(recordId)];
    if (!record || !Array.isArray(record.photos) || !record.photos.length) return;
    currentAlbum = record.photos.slice();
    showPhoto(index);
  }

  function showPhoto(index) {
    if (!photoViewer || !photoViewerImg) return;
    if (!currentAlbum.length) return;
    const nextIndex = Math.max(0, Math.min(index, currentAlbum.length - 1));
    currentPhotoIndex = nextIndex;
    const photo = currentAlbum[currentPhotoIndex];
    if (!photo) return;
    const src = photo.full || photo.thumb || '';
    photoViewerImg.src = src;
    photoViewer.classList.add('active');
  }

  function closePhotoViewer() {
    if (!photoViewer) return;
    photoViewer.classList.remove('active');
    currentAlbum = [];
    currentPhotoIndex = 0;
  }

  function triggerPhotoCapture(recordId) {
    const id = recordId || currentWorkRecordId;
    if (!id) {
      alert('Nejdřív vyberte strom v mapě.');
      return;
    }
    captureRecordId = id;
    if (photoCaptureInput) {
      photoCaptureInput.value = '';
      photoCaptureInput.click();
    }
  }

  function uploadCapturedPhoto() {
    if (!captureFile || !captureRecordId) {
      alert('Chybí fotka nebo úkon.');
      return;
    }
    if (!cfg.mapUploadPhotoUrl) {
      alert('Chybí konfigurace pro nahrání fotky.');
      return;
    }
    if (!captureSaveBtn) return;
    captureSaveBtn.disabled = true;

    const formData = new FormData();
    const baseComment = captureCommentInput ? captureCommentInput.value.trim() : '';
    const todayStr = new Date().toLocaleDateString('cs-CZ');
    const finalComment = baseComment ? todayStr + ' – ' + baseComment : todayStr;
    formData.append('record_id', captureRecordId);
    formData.append('photo', captureFile);
    formData.append('comment', finalComment);

    const headers = {};
    if (cfg.csrfToken) headers['X-CSRFToken'] = cfg.csrfToken;

    fetch(cfg.mapUploadPhotoUrl, {
      method: 'POST',
      headers: headers,
      body: formData,
    })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        if (data.status === 'ok') {
          closeCaptureModal();
          openWorkRecordPanel(captureRecordId);
        } else {
          alert(data.msg || 'Nepodařilo se uložit fotku.');
        }
      })
      .catch(function () {
        alert('Chyba při ukládání fotky.');
      })
      .finally(function () {
        captureSaveBtn.disabled = false;
      });
  }

  function openCaptureModal() {
    if (photoCaptureModal) photoCaptureModal.classList.add('active');
  }

  function closeCaptureModal() {
    if (photoCaptureModal) photoCaptureModal.classList.remove('active');
    captureFile = null;
    captureRecordId = null;
    if (photoCaptureInput) photoCaptureInput.value = '';
    if (captureCommentInput) captureCommentInput.value = '';
    if (captureCommentWrap) captureCommentWrap.classList.remove('show');
    if (capturePreview) capturePreview.src = '';
  }

  // ----- Assessment -----

  function updateSliderLabel(inputEl, labelEl) {
    if (!inputEl || !labelEl) return;
    labelEl.textContent = inputEl.value || '–';
  }

  function perspectiveLetterFromSlider(val) {
    const n = Number(val);
    if (n === 1) return 'a';
    if (n === 2) return 'b';
    if (n === 3) return 'c';
    return null;
  }

  function perspectiveLabelFromLetter(letter) {
    if (letter === 'a') return 'a – dlouhodobě perspektivní';
    if (letter === 'b') return 'b – krátkodobě perspektivní';
    if (letter === 'c') return 'c – neperspektivní';
    return '(nenastaveno)';
  }

  function perspectiveSliderValueFromLetter(letter) {
    if (letter === 'a') return 1;
    if (letter === 'b') return 2;
    if (letter === 'c') return 3;
    return 1;
  }

  function openAssessmentForRecord(recordId) {
    if (!assessmentModal || !cfg.assessmentApiBase || !recordId) return;
    if (assessmentWorkRecordIdInput) assessmentWorkRecordIdInput.value = recordId;
    if (assessmentDbhInput) assessmentDbhInput.value = '';
    if (assessmentHeightInput) assessmentHeightInput.value = '';
    if (assessmentPhysAge) assessmentPhysAge.value = 3;
    if (assessmentVitality) assessmentVitality.value = 3;
    if (assessmentHealth) assessmentHealth.value = 3;
    if (assessmentStability) assessmentStability.value = 3;
    if (assessmentPerspectiveSlider) {
      assessmentPerspectiveSlider.value = 1;
      if (assessmentPerspectiveValue) {
        assessmentPerspectiveValue.textContent = perspectiveLabelFromLetter('a');
      }
    }
    updateSliderLabel(assessmentPhysAge, assessmentPhysAgeValue);
    updateSliderLabel(assessmentVitality, assessmentVitalityValue);
    updateSliderLabel(assessmentHealth, assessmentHealthValue);
    updateSliderLabel(assessmentStability, assessmentStabilityValue);
    if (assessmentMessage) {
      assessmentMessage.textContent = '';
      assessmentMessage.className = 'mt-2 small';
    }

    const url = String(cfg.assessmentApiBase).replace(/\/?$/, '/') + recordId + '/assessment/';
    assessmentModal.classList.add('active');

    fetch(url, {
      method: 'GET',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('Failed to load assessment');
        return resp.json();
      })
      .then(function (data) {
        if (assessmentDbhInput && data.dbh_cm != null) {
          assessmentDbhInput.value = data.dbh_cm;
        }
        if (assessmentHeightInput && data.height_m != null) {
          assessmentHeightInput.value = data.height_m;
        }
        if (assessmentPhysAge && data.physiological_age) {
          assessmentPhysAge.value = data.physiological_age;
        }
        if (assessmentVitality && data.vitality) {
          assessmentVitality.value = data.vitality;
        }
        if (assessmentHealth && data.health_state) {
          assessmentHealth.value = data.health_state;
        }
        if (assessmentStability && data.stability) {
          assessmentStability.value = data.stability;
        }
        if (assessmentPerspectiveSlider && assessmentPerspectiveValue && data.perspective) {
          const letter = data.perspective;
          assessmentPerspectiveSlider.value = perspectiveSliderValueFromLetter(letter);
          assessmentPerspectiveValue.textContent = perspectiveLabelFromLetter(letter);
        }
        updateSliderLabel(assessmentPhysAge, assessmentPhysAgeValue);
        updateSliderLabel(assessmentVitality, assessmentVitalityValue);
        updateSliderLabel(assessmentHealth, assessmentHealthValue);
        updateSliderLabel(assessmentStability, assessmentStabilityValue);
      })
      .catch(function () {
        if (assessmentMessage) {
          assessmentMessage.textContent = 'Nepodařilo se načíst hodnocení.';
          assessmentMessage.className = 'mt-2 small text-danger';
        }
      });
  }

  function hideAssessmentModal() {
    if (!assessmentModal) return;
    assessmentModal.classList.remove('active');
    if (assessmentMessage) {
      assessmentMessage.textContent = '';
      assessmentMessage.className = 'mt-2 small';
    }
  }

  function submitAssessment() {
    if (!assessmentModal || !cfg.assessmentApiBase) return;
    const recordId = assessmentWorkRecordIdInput ? assessmentWorkRecordIdInput.value : null;
    if (!recordId) {
      alert('Chybí ID úkonu.');
      return;
    }
    const url = String(cfg.assessmentApiBase).replace(/\/?$/, '/') + recordId + '/assessment/';
    const payload = {
      dbh_cm: assessmentDbhInput && assessmentDbhInput.value ? assessmentDbhInput.value : null,
      height_m:
        assessmentHeightInput && assessmentHeightInput.value ? assessmentHeightInput.value : null,
      physiological_age:
        assessmentPhysAge && assessmentPhysAge.value ? assessmentPhysAge.value : null,
      vitality: assessmentVitality && assessmentVitality.value ? assessmentVitality.value : null,
      health_state:
        assessmentHealth && assessmentHealth.value ? assessmentHealth.value : null,
      stability:
        assessmentStability && assessmentStability.value ? assessmentStability.value : null,
      perspective: assessmentPerspectiveSlider
        ? perspectiveLetterFromSlider(assessmentPerspectiveSlider.value)
        : null,
    };

    if (assessmentSaveBtn) assessmentSaveBtn.disabled = true;

    const headers = {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    };
    if (cfg.csrfToken) headers['X-CSRFToken'] = cfg.csrfToken;

    fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(payload),
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('Save failed');
        return resp.json();
      })
      .then(function () {
        hideAssessmentModal();
        openWorkRecordPanel(recordId);
      })
      .catch(function () {
        if (assessmentMessage) {
          assessmentMessage.textContent = 'Chyba při ukládání hodnocení.';
          assessmentMessage.className = 'mt-2 small text-danger';
        }
      })
      .finally(function () {
        if (assessmentSaveBtn) assessmentSaveBtn.disabled = false;
      });
  }

  // ----- Intervention -----

  function buildInterventionApiUrl(recordId) {
    if (!interventionApiTemplate) return '';
    return interventionApiTemplate.replace('/0/', '/' + recordId + '/');
  }

  function setInterventionMessage(text, isError) {
    if (!interventionFormErrors) return;
    interventionFormErrors.textContent = text || '';
    interventionFormErrors.className = isError
      ? 'mt-2 text-danger small'
      : 'mt-2 text-success small';
  }

  function formatInterventionErrors(errors) {
    const parts = [];
    for (const key in errors) {
      if (!Object.prototype.hasOwnProperty.call(errors, key)) continue;
      const items = errors[key] || [];
      items.forEach(function (item) {
        if (item && item.message) {
          parts.push(item.message);
        }
      });
    }
    return parts.join(' ');
  }

  function updateInterventionNoteHint() {
    if (!interventionNoteHintModal || !interventionTypeSelect) return;
    const data = cfg.interventionNoteData
      ? cfg.interventionNoteData[interventionTypeSelect.value]
      : null;
    if (data && data.note_required) {
      interventionNoteHintModal.textContent = data.note_hint || 'Vyžaduje doplnění poznámky.';
    } else {
      interventionNoteHintModal.textContent = '';
    }
  }

  function getInterventions(recordId) {
    const rec = recordCache[Number(recordId)] || {};
    return Array.isArray(rec.interventions) ? rec.interventions.slice() : [];
  }

  function setInterventions(recordId, items) {
    const rec = recordCache[Number(recordId)] || { id: Number(recordId) };
    rec.interventions = items.slice();
    cacheRecord(rec);
  }

  function renderInterventionList(items) {
    if (!interventionListContainer) return;
    if (!items || !items.length) {
      interventionListContainer.innerHTML =
        '<p class="text-muted mb-1">Zatím nejsou zadány žádné zásahy.</p>';
      return;
    }
    let html = '';
    html += '<div class="mb-1"><strong>Existující zásahy</strong></div>';
    html += '<div><table class="table table-sm mb-1"><thead><tr>';
    html += '<th>Kód</th><th>Název</th><th>Stav</th><th>Vytvořeno</th><th></th>';
    html += '</tr></thead><tbody>';
    items.forEach(function (item) {
      const created = item.created_at || '';
      const handed = item.handed_over_for_check_at || null;
      let label = '';
      if (handed) {
        label = 'Předáno ke kontrole';
      } else if (created) {
        label = 'Vytvořeno';
      }
      html += '<tr>';
      html += '<td>' + (item.code || '') + '</td>';
      html += '<td>' + (item.name || '') + '</td>';
      html += '<td>' + (item.status || '') + '</td>';
      html += '<td>';
      if (label || created || handed) {
        const ts = handed || created;
        html += '<div class="small text-muted">';
        if (label) html += label + ': ';
        html += ts ? new Date(ts).toLocaleString('cs-CZ') : '-';
        html += '</div>';
      } else {
        html += '<span class="text-muted">-</span>';
      }
      html += '</td>';
      html += '<td class="text-end">';
      if (item.status_code === 'approved' || item.status_code === 'in_progress') {
        html +=
          '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="handover" data-intervention-id="' +
          item.id +
          '" title="Předat ke kontrole"><i class="bi bi-send-check"></i></button>';
      }
      html += '</td>';
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    interventionListContainer.innerHTML = html;
  }

  function loadInterventionsForRecord(recordId) {
    if (!interventionModal || !interventionForm || !recordId) return;
    if (!interventionListContainer) return;
    const url = buildInterventionApiUrl(recordId);
    if (!url) return;
    interventionListContainer.innerHTML = '<p class="text-muted mb-1">Načítám zásahy…</p>';
    fetch(url, {
      method: 'GET',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (resp) {
        return resp.ok ? resp.json() : Promise.reject();
      })
      .then(function (body) {
        if (!body || body.status !== 'ok') return;
        const interventions = body.interventions || [];
        setInterventions(recordId, interventions);
        renderInterventionList(interventions);
      })
      .catch(function () {
        interventionListContainer.innerHTML =
          '<p class="text-danger mb-1">Nepodařilo se načíst zásahy.</p>';
      });
  }

  function handoverIntervention(recordId, interventionId, buttonEl) {
    const url = buildInterventionApiUrl(recordId);
    if (!url) return;
    const payload = new URLSearchParams();
    payload.set('action', 'handover');
    payload.set('id', String(interventionId));
    if (buttonEl) buttonEl.disabled = true;
    const headers = {
      'X-Requested-With': 'XMLHttpRequest',
      'Content-Type': 'application/x-www-form-urlencoded',
    };
    if (cfg.csrfToken) headers['X-CSRFToken'] = cfg.csrfToken;
    fetch(url, {
      method: 'POST',
      headers: headers,
      body: payload.toString(),
    })
      .then(function (resp) {
        return resp.json().then(function (body) {
          return { status: resp.status, body: body };
        });
      })
      .then(function (result) {
        if (result.status >= 400 || !result.body || result.body.status !== 'ok') {
          throw result.body;
        }
        loadInterventionsForRecord(recordId);
      })
      .catch(function () {
        setInterventionMessage('Nepodařilo se předat zásah ke kontrole.', true);
      })
      .finally(function () {
        if (buttonEl) buttonEl.disabled = false;
      });
  }

  function openInterventionModal(recordId) {
    if (!interventionModal || !interventionForm || !recordId) return;
    if (interventionTreeIdInput) {
      interventionTreeIdInput.value = recordId;
    }
    const action = buildInterventionApiUrl(recordId);
    if (action) {
      interventionForm.action = action;
    }
    setInterventionMessage('', true);
    updateInterventionNoteHint();
    loadInterventionsForRecord(recordId);
    interventionModal.classList.add('active');
  }

  function hideInterventionModal() {
    if (!interventionModal) return;
    interventionModal.classList.remove('active');
  }

  function submitInterventionForm(event) {
    if (event) event.preventDefault();
    if (!interventionForm) return;
    const action = interventionForm.action;
    const payload = new FormData(interventionForm);
    const recordId = interventionTreeIdInput ? interventionTreeIdInput.value : null;
    if (interventionTreeIdInput && recordId) {
      payload.set('tree_id', recordId);
    }
    if (interventionSaveBtn) interventionSaveBtn.disabled = true;
    const headers = { 'X-Requested-With': 'XMLHttpRequest' };
    if (cfg.csrfToken) headers['X-CSRFToken'] = cfg.csrfToken;

    fetch(action, {
      method: 'POST',
      headers: headers,
      body: payload,
    })
      .then(function (resp) {
        return resp.json().then(function (body) {
          return { status: resp.status, body: body };
        });
      })
      .then(function (result) {
        if (result.status >= 400 || !result.body || result.body.status !== 'ok') {
          throw result.body;
        }
        const data = result.body;
        const rid = recordId || (interventionTreeIdInput ? interventionTreeIdInput.value : null);
        if (interventionForm) {
          interventionForm.reset();
          if (interventionTreeIdInput && rid) {
            interventionTreeIdInput.value = rid;
          }
        }
        const current = rid ? getInterventions(rid) : [];
        if (data && data.intervention && rid) {
          const idx = current.findIndex(function (i) {
            return Number(i.id) === Number(data.intervention.id);
          });
          if (idx >= 0) current[idx] = data.intervention;
          else current.unshift(data.intervention);
          setInterventions(rid, current);
          renderInterventionList(current);
        } else if (rid) {
          loadInterventionsForRecord(rid);
        }
        setInterventionMessage('Zásah byl uložen.', false);
        hideInterventionModal();
        console.debug('intervention saved', { recordId: rid });
      })
      .catch(function (err) {
        if (err && err.errors) {
          setInterventionMessage(formatInterventionErrors(err.errors), true);
        } else if (err && err.msg) {
          setInterventionMessage(err.msg, true);
        } else {
          setInterventionMessage('Nepodařilo se uložit zásah.', true);
        }
      })
      .finally(function () {
        if (interventionSaveBtn) interventionSaveBtn.disabled = false;
      });
  }

  // ----- DOM init -----

  function initDom() {
    bottomPanel = document.getElementById('bottom-panel');
    treePanel = document.getElementById('tree-panel');
    backLink = document.getElementById('mapBackLink');
    backLinkDefaultHref = backLink ? backLink.getAttribute('href') : null;

    if (treePanel) {
      treePanel.addEventListener('click', function (event) {
        if (event.target.closest('.tree-panel-close')) {
          event.preventDefault();
          closeTreePanel();
        }
      });
    }

    // Photo viewer / capture
    photoViewer = document.getElementById('photoViewer');
    if (photoViewer) {
      photoViewerImg = photoViewer.querySelector('img');
      photoViewerPrev = photoViewer.querySelector('.pv-prev');
      photoViewerNext = photoViewer.querySelector('.pv-next');
      photoViewerClose = photoViewer.querySelector('.pv-close');

      photoViewer.addEventListener('click', function (e) {
        if (e.target === photoViewer) closePhotoViewer();
      });
      if (photoViewerClose) {
        photoViewerClose.addEventListener('click', function () {
          closePhotoViewer();
        });
      }
      if (photoViewerPrev) {
        photoViewerPrev.addEventListener('click', function (e) {
          e.stopPropagation();
          if (!currentAlbum.length) return;
          const next = (currentPhotoIndex - 1 + currentAlbum.length) % currentAlbum.length;
          showPhoto(next);
        });
      }
      if (photoViewerNext) {
        photoViewerNext.addEventListener('click', function (e) {
          e.stopPropagation();
          if (!currentAlbum.length) return;
          const next = (currentPhotoIndex + 1) % currentAlbum.length;
          showPhoto(next);
        });
      }
      document.addEventListener('keydown', function (e) {
        if (!photoViewer || !photoViewer.classList.contains('active')) return;
        if (e.key === 'Escape') closePhotoViewer();
        if (e.key === 'ArrowRight') {
          const next = (currentPhotoIndex + 1) % currentAlbum.length;
          showPhoto(next);
        }
        if (e.key === 'ArrowLeft') {
          const next = (currentPhotoIndex - 1 + currentAlbum.length) % currentAlbum.length;
          showPhoto(next);
        }
      });
    }

    photoCaptureInput = document.getElementById('photoCaptureInput');
    photoCaptureModal = document.getElementById('photoCaptureModal');
    capturePreview = document.getElementById('capturePreview');
    captureCommentInput = document.getElementById('captureCommentInput');
    captureCommentToggle = document.getElementById('captureCommentToggle');
    captureCommentWrap = document.getElementById('captureCommentWrap');
    captureSaveBtn = document.getElementById('captureSaveBtn');
    captureCancelBtn = document.getElementById('captureCancelBtn');

    if (photoCaptureInput) {
      photoCaptureInput.addEventListener('change', function (event) {
        const file = event.target.files && event.target.files[0];
        if (!file) return;
        const compress = window.setCompressedFileToInput;
        if (typeof compress === 'function') {
          (async function () {
            try {
              await compress(photoCaptureInput, file, capturePreview);
              const compressed = photoCaptureInput.files && photoCaptureInput.files[0];
              captureFile = compressed || file;
              openCaptureModal();
            } catch (err) {
              console.error('Compression failed', err);
              captureFile = file;
              const reader = new FileReader();
              reader.onload = function (ev) {
                if (capturePreview) capturePreview.src = ev.target.result;
                openCaptureModal();
              };
              reader.readAsDataURL(file);
            }
          })();
        } else {
          captureFile = file;
          const reader = new FileReader();
          reader.onload = function (ev) {
            if (capturePreview) capturePreview.src = ev.target.result;
            openCaptureModal();
          };
          reader.readAsDataURL(file);
        }
      });
    }
    if (captureCommentToggle && captureCommentWrap) {
      captureCommentToggle.addEventListener('click', function () {
        captureCommentWrap.classList.toggle('show');
      });
    }
    if (captureCancelBtn) {
      captureCancelBtn.addEventListener('click', closeCaptureModal);
    }
    if (captureSaveBtn) {
      captureSaveBtn.addEventListener('click', uploadCapturedPhoto);
    }
    if (photoCaptureModal) {
      photoCaptureModal.addEventListener('click', function (e) {
        if (e.target === photoCaptureModal) closeCaptureModal();
      });
    }

    // Assessment modal
    assessmentModal = document.getElementById('assessmentModal');
    assessmentWorkRecordIdInput = document.getElementById('assessmentWorkRecordId');
    assessmentDbhInput = document.getElementById('assessmentDbh');
    assessmentHeightInput = document.getElementById('assessmentHeight');
    assessmentPhysAge = document.getElementById('assessmentPhysAge');
    assessmentVitality = document.getElementById('assessmentVitality');
    assessmentHealth = document.getElementById('assessmentHealth');
    assessmentStability = document.getElementById('assessmentStability');
    assessmentPhysAgeValue = document.getElementById('assessmentPhysAgeValue');
    assessmentVitalityValue = document.getElementById('assessmentVitalityValue');
    assessmentHealthValue = document.getElementById('assessmentHealthValue');
    assessmentStabilityValue = document.getElementById('assessmentStabilityValue');
    assessmentPerspectiveSlider = document.getElementById('assessmentPerspectiveSlider');
    assessmentPerspectiveValue = document.getElementById('assessmentPerspectiveValue');
    assessmentSaveBtn = document.getElementById('assessmentSaveBtn');
    assessmentCancelBtn = document.getElementById('assessmentCancelBtn');
    assessmentCloseBtn = document.getElementById('assessmentCloseBtn');
    assessmentMessage = document.getElementById('assessmentMessage');

    [assessmentPhysAge, assessmentVitality, assessmentHealth, assessmentStability].forEach(
      function (inputEl, idx) {
        if (!inputEl) return;
        const labelMap = [
          assessmentPhysAgeValue,
          assessmentVitalityValue,
          assessmentHealthValue,
          assessmentStabilityValue,
        ];
        const labelEl = labelMap[idx];
        inputEl.addEventListener('input', function () {
          updateSliderLabel(inputEl, labelEl);
        });
      }
    );

    if (assessmentPerspectiveSlider && assessmentPerspectiveValue) {
      assessmentPerspectiveSlider.addEventListener('input', function () {
        const letter = perspectiveLetterFromSlider(assessmentPerspectiveSlider.value);
        assessmentPerspectiveValue.textContent = perspectiveLabelFromLetter(letter);
      });
    }
    if (assessmentCancelBtn) {
      assessmentCancelBtn.addEventListener('click', hideAssessmentModal);
    }
    if (assessmentCloseBtn) {
      assessmentCloseBtn.addEventListener('click', hideAssessmentModal);
    }
    if (assessmentModal) {
      assessmentModal.addEventListener('click', function (e) {
        if (e.target === assessmentModal) hideAssessmentModal();
      });
    }
    if (assessmentSaveBtn) {
      assessmentSaveBtn.addEventListener('click', submitAssessment);
    }

    // Intervention modal
    interventionModal = document.getElementById('interventionModal');
    interventionForm = document.getElementById('interventionForm');
    interventionTreeIdInput = document.getElementById('interventionTreeId');
    interventionCloseBtn = document.getElementById('interventionCloseBtn');
    interventionCancelBtn = document.getElementById('interventionCancelBtn');
    interventionSaveBtn = document.getElementById('interventionSaveBtn');
    interventionNoteHintModal = document.getElementById('interventionNoteHintModal');
    interventionFormErrors = document.getElementById('interventionFormErrors');
    interventionTypeSelect = document.getElementById('id_intervention_type');
    interventionListContainer = document.getElementById('intervention-list');
    if (interventionModal) {
      interventionApiTemplate = interventionModal.dataset.apiTemplate || '';
    }

    if (interventionModal && interventionForm && !interventionListContainer) {
      interventionListContainer = document.createElement('div');
      interventionListContainer.id = 'intervention-list';
      interventionListContainer.className = 'mb-2 small';
      interventionForm.parentNode.insertBefore(interventionListContainer, interventionForm);
    }

    if (interventionCloseBtn) {
      interventionCloseBtn.addEventListener('click', hideInterventionModal);
    }
    if (interventionCancelBtn) {
      interventionCancelBtn.addEventListener('click', hideInterventionModal);
    }
    if (interventionModal) {
      interventionModal.addEventListener('click', function (e) {
        if (e.target === interventionModal) hideInterventionModal();
      });
    }
    if (interventionForm) {
      interventionForm.addEventListener('submit', submitInterventionForm);
      if (interventionTypeSelect) {
        interventionTypeSelect.addEventListener('change', updateInterventionNoteHint);
      }
    }
    if (interventionListContainer) {
      interventionListContainer.addEventListener('click', function (e) {
        const btn = e.target.closest('[data-action="handover"]');
        if (!btn) return;
        const recordId = interventionTreeIdInput ? interventionTreeIdInput.value : null;
        const interventionId = btn.getAttribute('data-intervention-id');
        if (!recordId || !interventionId) return;
        handoverIntervention(recordId, interventionId, btn);
      });
    }

    document.addEventListener(
      'click',
      function (event) {
        const thumb = event.target.closest('.wr-photo-thumb');
        if (!thumb) return;
        event.preventDefault();
        const recordId = thumb.getAttribute('data-record-id');
        const index = Number(thumb.getAttribute('data-photo-index')) || 0;
        openPhotoViewer(recordId, index);
      },
      true
    );
  }

  function init() {
    mergeConfig();
    initDom();
    window.openWorkRecordPanel = openWorkRecordPanel;
    window.closeWorkRecordPanel = closeTreePanel;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
