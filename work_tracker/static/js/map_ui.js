;(function () {
  'use strict';

  const cfg = {
    workRecordDetailApiBase: null,
    assessmentApiBase: null,
    mapUploadPhotoUrl: null,
    projectId: null,
    addToProjectUrlTemplate: null,
    disableLocationConfirmFab: false,
    csrfToken: null,
    interventionNoteData: {},
    workRecordSetLocationUrlTemplate: null,
  };
  const debugEnabled = typeof window !== 'undefined' && window.DEBUG_MAP_UI;

  const recordCache = {};
  let currentWorkRecordId = null;
  let moveLocationMode = false;
  let moveTargetId = null;
  let pendingLngLat = null;

  let bottomPanel;
  let treePanel;
  let backLink;
  let backLinkDefaultHref;
  let menuButton;
  let controlsPanel;
  let projectTitle;
  let workrecordPanelActions;
  let moveLocationBanner;
  let moveLocationCancelBtn;
  let moveLocationSaveBtn;
  let moveLocationMessage;

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
  let assessmentCrownWidthInput;
  let assessmentCrownAreaInput;
  let assessmentCrownAreaHint;
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
  let interventionDescriptionWrap;
  let interventionDescriptionToggle;
  let interventionDescriptionInput;
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
    if (userCfg.projectId !== undefined && userCfg.projectId !== null && userCfg.projectId !== '') {
      cfg.projectId = userCfg.projectId;
    }
    if (userCfg.addToProjectUrlTemplate) {
      cfg.addToProjectUrlTemplate = userCfg.addToProjectUrlTemplate;
    }
    if (userCfg.disableLocationConfirmFab !== undefined && userCfg.disableLocationConfirmFab !== null) {
      cfg.disableLocationConfirmFab = Boolean(userCfg.disableLocationConfirmFab);
    }
    if (userCfg.csrfToken) {
      cfg.csrfToken = userCfg.csrfToken;
    }
    if (userCfg.interventionNoteData) {
      cfg.interventionNoteData = userCfg.interventionNoteData || {};
    }
    if (userCfg.workRecordSetLocationUrlTemplate) {
      cfg.workRecordSetLocationUrlTemplate = userCfg.workRecordSetLocationUrlTemplate;
    }
    if (debugEnabled) {
      console.debug('map_ui config', {
        projectId: cfg.projectId,
        addToProjectUrlTemplate: cfg.addToProjectUrlTemplate,
        disableLocationConfirmFab: cfg.disableLocationConfirmFab,
      });
    }
  }

  function findProjectName(projectId) {
    if (!projectId) return '';
    const dataEl = document.getElementById('projects-data');
    if (!dataEl) return '';
    try {
      const projects = JSON.parse(dataEl.textContent);
      if (!Array.isArray(projects)) return '';
      const match = projects.find(function (item) {
        return item && String(item.id) === String(projectId);
      });
      return match && match.name ? String(match.name) : '';
    } catch (e) {
      return '';
    }
  }

  function updateProjectTitle() {
    if (!projectTitle) return;
    const defaultTitle = projectTitle.getAttribute('data-default-title') || 'Mapa';
    const projectId = cfg.projectId ? String(cfg.projectId) : '';
    const resolved = findProjectName(projectId);
    projectTitle.textContent = resolved || defaultTitle;
  }

  function setControlsOpen(nextOpen) {
    if (!controlsPanel) return;
    controlsPanel.classList.toggle('open', nextOpen);
    controlsPanel.setAttribute('aria-hidden', nextOpen ? 'false' : 'true');
    if (menuButton) {
      menuButton.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
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
    if (workrecordPanelActions) {
      workrecordPanelActions.innerHTML = '';
    }
    cancelMoveLocationMode();
  }

  function getSetLocationUrl(recordId) {
    if (!cfg.workRecordSetLocationUrlTemplate) return null;
    return cfg.workRecordSetLocationUrlTemplate.replace('/0/set_location/', '/' + recordId + '/set_location/');
  }

  function updateMoveLocationBanner() {
    if (!moveLocationBanner) return;
    moveLocationBanner.classList.toggle('active', moveLocationMode);
    moveLocationBanner.setAttribute('aria-hidden', moveLocationMode ? 'false' : 'true');
    if (moveLocationSaveBtn) {
      moveLocationSaveBtn.disabled = !pendingLngLat;
    }
  }

  function setMoveLocationMessage(message, isError) {
    if (!moveLocationMessage) return;
    moveLocationMessage.textContent = message || '';
    moveLocationMessage.classList.toggle('error', !!isError);
  }

  function normalizeLngLat(lngLat) {
    if (!lngLat) return null;
    if (typeof lngLat.lng === 'number' && typeof lngLat.lat === 'number') {
      return { lng: lngLat.lng, lat: lngLat.lat };
    }
    if (Array.isArray(lngLat) && lngLat.length >= 2) {
      const lng = Number(lngLat[0]);
      const lat = Number(lngLat[1]);
      if (Number.isFinite(lng) && Number.isFinite(lat)) {
        return { lng: lng, lat: lat };
      }
    }
    return null;
  }

  function setPendingMoveLocation(lngLat) {
    if (!moveLocationMode) return;
    const normalized = normalizeLngLat(lngLat);
    if (!normalized) return;
    pendingLngLat = normalized;
    setMoveLocationMessage('');
    updateMoveLocationBanner();
  }

  function enterMoveLocationMode(recordId) {
    if (!recordId) return;
    const idNum = Number(recordId);
    if (!Number.isFinite(idNum)) return;
    if (!getSetLocationUrl(idNum)) return;
    const record = recordCache[idNum];
    if (record && !record.can_edit) return;
    moveLocationMode = true;
    moveTargetId = idNum;
    pendingLngLat = null;
    setMoveLocationMessage('');
    updateMoveLocationBanner();
    renderPanelActions(recordCache[idNum]);
  }

  function cancelMoveLocationMode() {
    if (!moveLocationMode && !pendingLngLat) return;
    moveLocationMode = false;
    moveTargetId = null;
    pendingLngLat = null;
    updateMoveLocationBanner();
    setMoveLocationMessage('');
    if (typeof window.clearMoveLocationMarker === 'function') {
      window.clearMoveLocationMarker();
    }
    renderPanelActions(currentWorkRecordId ? recordCache[currentWorkRecordId] : null);
  }

  function submitMoveLocation() {
    if (!moveLocationMode || !moveTargetId || !pendingLngLat) return;
    const url = getSetLocationUrl(moveTargetId);
    if (!url) return;
    if (moveLocationSaveBtn) moveLocationSaveBtn.disabled = true;
    const payload = new URLSearchParams();
    payload.set('latitude', pendingLngLat.lat);
    payload.set('longitude', pendingLngLat.lng);
    const headers = { 'X-Requested-With': 'XMLHttpRequest' };
    if (cfg.csrfToken) headers['X-CSRFToken'] = cfg.csrfToken;
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
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
        if (result.status >= 400 || !result.body) {
          const message = (result.body && result.body.error) || 'Nepodařilo se uložit polohu.';
          throw new Error(message);
        }
        const updated = {
          id: moveTargetId,
          latitude: result.body.latitude,
          longitude: result.body.longitude,
        };
        const cached = recordCache[Number(moveTargetId)];
        if (cached) {
          cached.lat = updated.latitude;
          cached.lon = updated.longitude;
          cached.latitude = updated.latitude;
          cached.longitude = updated.longitude;
          cacheRecord(cached);
        }
        if (typeof window.updateWorkrecordLocationInMap === 'function') {
          window.updateWorkrecordLocationInMap(moveTargetId, {
            lng: updated.longitude,
            lat: updated.latitude,
          });
        }
        cancelMoveLocationMode();
      })
      .catch(function (err) {
        const message = err && err.message ? err.message : 'Nepodařilo se uložit polohu.';
        setMoveLocationMessage(message, true);
      })
      .finally(function () {
        if (moveLocationSaveBtn && moveLocationMode) moveLocationSaveBtn.disabled = !pendingLngLat;
      });
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

  function buildReturnUrlParam() {
    try {
      if (!window.location) return '';
      const currentUrl = window.location.pathname + window.location.search;
      return encodeURIComponent(currentUrl);
    } catch (e) {
      return '';
    }
  }

  function buildDetailUrl(recordId) {
    const detailUrl = '/tracker/' + recordId + '/';
    const projectId = getProjectContextId();
    const returnParam = buildReturnUrlParam();
    if (!projectId && !returnParam) return detailUrl;
    const params = [];
    if (projectId) params.push('project=' + encodeURIComponent(projectId));
    if (returnParam) params.push('return=' + returnParam);
    return detailUrl + '?' + params.join('&');
  }

  function buildPopupHtml(record, state, opts) {
    const detailUrl = buildDetailUrl(record.id);
    const displayLabel = getRecordDisplayLabel(record);
    const taxon = record.taxon || '';
    const options = opts || {};
    const taxonHtml = taxon.trim()
      ? '<span class="wr-sep">·</span><span class="wr-taxon">' + taxon.trim() + '</span>'
      : '';
    const assessClass = record.has_assessment
      ? 'wr-popup-btn assess has-assessment'
      : 'wr-popup-btn assess';
    const addToProjectEnabled = Boolean(options.addToProjectEnabled);
    const addedToProject = Boolean(record && (record.in_project || record.added_to_project));
    const addToProjectMessage = record && record.add_to_project_message ? record.add_to_project_message : '';
    const addToProjectIcon = addedToProject ? 'bi bi-check-circle' : 'bi bi-folder-plus';
    const addToProjectButtonHtml = addToProjectEnabled
      ? '<button type="button" class="wr-popup-btn intervention add-to-project" data-action="add_to_project" data-record-id="' +
        record.id +
        '"' +
        (addedToProject ? ' disabled' : '') +
        ' title="' +
        (addedToProject ? 'V projektu' : 'Přidat do projektu') +
        '"><i class="' +
        addToProjectIcon +
        '"></i></button>'
      : '';
    const addToProjectMessageHtml = addToProjectEnabled
      ? '<div class="wr-popup-message small mt-1" data-role="add-to-project-message">' +
        addToProjectMessage +
        '</div>'
      : '';

    return (
      '<div class="wr-popup">' +
      '<div class="wr-header">' +
      '<a href="' +
      detailUrl +
      '" class="wr-title">' +
      displayLabel +
      '</a>' +
      taxonHtml +
      '</div>' +
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
      addToProjectButtonHtml +
      (record.can_edit && getSetLocationUrl(record.id)
        ? '<button type="button" class="wr-popup-btn move-location" data-action="move-location" data-record-id="' +
          record.id +
          '" title="Upravit polohu"><i class="bi bi-geo-alt"></i></button>'
        : '') +
      '</div>' +
      addToProjectMessageHtml +
      '</div>'
    );
  }

  function getProjectContextId() {
    if (cfg.projectId) return String(cfg.projectId);
    try {
      const urlId = new URLSearchParams(window.location.search).get('project');
      return urlId || '';
    } catch (e) {
      return '';
    }
  }

  function getAddToProjectTemplate() {
    return cfg.addToProjectUrlTemplate || '/tracker/projects/0/trees/0/add/';
  }

  function buildAddToProjectHtml(record, state) {
    const projectId = getProjectContextId();
    const template = getAddToProjectTemplate();
    if (!projectId || !template) return '';
    const statusText = (state && state.addToProjectMessage) ? state.addToProjectMessage : '';
    const buttonLabel = (state && state.addedToProject) ? 'V projektu' : 'Přidat do projektu';
    const disabledAttr = (state && state.addedToProject) ? ' disabled' : '';
    return (
      '<div class="mt-2">' +
      '<button type="button" class="btn btn-sm btn-outline-primary" data-action="add-to-project" data-record-id="' +
      record.id +
      '"' +
      disabledAttr +
      '>' +
      buttonLabel +
      '</button>' +
      '<div class="small mt-1" data-role="add-to-project-message">' +
      statusText +
      '</div>' +
      '</div>'
    );
  }

  function renderPanelActions(record) {
    if (!workrecordPanelActions) return;
    workrecordPanelActions.innerHTML = '';
  }

  function renderTreePanel(record, state) {
    if (!treePanel || !record) return;
    if (currentWorkRecordId !== Number(record.id)) return;
    const debugMode = !!debugEnabled;
    const addToProjectEnabled = Boolean(getProjectContextId());
    const html =
      '<div class="tree-panel-inner">' +
      '<div class="tree-panel-header">' +
      '</div>' +
      buildPopupHtml(record, state || {}, { addToProjectEnabled: addToProjectEnabled }) +
      '</div>';
    if (debugMode) {
      const htmlContainsAdd = html.indexOf('data-action="add_to_project"') !== -1;
      console.debug('map_ui renderTreePanel debug', {
        locationSearch: window.location ? window.location.search : '',
        projectContextId: (typeof getProjectContextId === 'function') ? getProjectContextId() : 'getProjectContextId missing',
        htmlContainsAdd: htmlContainsAdd,
      });
    }
    treePanel.innerHTML = html;
    renderPanelActions(record);
    if (debugMode) {
      const addBtn = treePanel.querySelector('[data-action="add_to_project"]');
      console.debug('map_ui renderTreePanel debug post', {
        elementExists: !!addBtn,
      });
      if (addBtn) {
        const styles = window.getComputedStyle(addBtn);
        console.debug('map_ui add-to-project styles', {
          display: styles.display,
          visibility: styles.visibility,
          rect: addBtn.getBoundingClientRect(),
        });
      }
    }
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
    treePanel.querySelectorAll('.wr-popup-btn[data-action="move-location"]').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        enterMoveLocationMode(record.id);
      });
    });
    const addButtons = treePanel.querySelectorAll('.wr-popup-btn[data-action="add_to_project"]');
    if (debugEnabled) {
      console.debug('map_ui add-to-project buttons found', addButtons.length);
    }
    addButtons.forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const messageEl = treePanel.querySelector('[data-role="add-to-project-message"]');
        handleAddToProject(record.id, btn, messageEl);
      });
    });
  }

  function buildAddToProjectUrl(recordId) {
    const projectId = getProjectContextId();
    const template = getAddToProjectTemplate();
    if (!projectId || !template) return null;
    return template.replace('/0/trees/0/add/', '/' + projectId + '/trees/' + recordId + '/add/');
  }

  function handleAddToProject(recordId, buttonEl, messageEl) {
    const url = buildAddToProjectUrl(recordId);
    if (!url) {
      if (buttonEl) {
        buttonEl.disabled = true;
      }
      return;
    }
    if (messageEl) {
      messageEl.textContent = 'Přidávám do projektu...';
      messageEl.className = 'wr-popup-message small mt-1 text-muted';
    }
    if (buttonEl) {
      buttonEl.disabled = true;
    }
    fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': cfg.csrfToken || '',
        'X-Requested-With': 'XMLHttpRequest',
      },
    })
      .then(function (resp) {
        return resp.json().then(function (body) {
          if (!resp.ok || !body || !body.ok) {
            const err = (body && body.error) || 'Chyba při přidání do projektu.';
            throw new Error(err);
          }
          return body;
        });
      })
      .then(function () {
        if (messageEl) {
          messageEl.textContent = 'Přidáno do projektu.';
          messageEl.className = 'wr-popup-message small mt-1 text-success';
        }
        if (buttonEl) {
          buttonEl.innerHTML = '<i class="bi bi-check-circle"></i>';
          buttonEl.disabled = true;
          buttonEl.title = 'V projektu';
        }
        const cached = recordCache[Number(recordId)];
        if (cached) {
          cached.in_project = true;
          cached.added_to_project = true;
          cached.add_to_project_message = 'Přidáno do projektu.';
          cacheRecord(cached);
        }
        if (typeof window.refreshProjectWorkrecords === 'function') {
          window.refreshProjectWorkrecords();
        }
      })
      .catch(function (err) {
        if (messageEl) {
          messageEl.textContent = err && err.message ? err.message : 'Nepodařilo se přidat strom do projektu.';
          messageEl.className = 'wr-popup-message small mt-1 text-danger';
        }
        if (buttonEl) {
          buttonEl.disabled = false;
        }
        const cached = recordCache[Number(recordId)];
        if (cached && messageEl) {
          cached.add_to_project_message = messageEl.textContent;
          cacheRecord(cached);
        }
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

    if (moveLocationMode && moveTargetId && moveTargetId !== idNum) {
      cancelMoveLocationMode();
    }
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
        in_project: prefill.inProject === true,
      };
      cacheRecord(baseRecord);
    } else if (prefill.label && (!baseRecord.title || baseRecord.title === 'Načítám…')) {
      baseRecord = { ...baseRecord, title: prefill.label };
      cacheRecord(baseRecord);
    }
    if (prefill.inProject !== undefined) {
      baseRecord = { ...baseRecord, in_project: prefill.inProject === true };
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
    labelEl.textContent = inputEl.value || '-';
  }

  function updateCrownAreaHint(areaValue, widthValue, heightValue) {
    if (assessmentCrownAreaInput) {
      assessmentCrownAreaInput.value = areaValue || '';
    }
    if (!assessmentCrownAreaHint) return;
    if (areaValue) {
      assessmentCrownAreaHint.textContent = '';
      return;
    }
    const widthNum = typeof widthValue === 'number' ? widthValue : parseFloat(widthValue);
    const heightNum = typeof heightValue === 'number' ? heightValue : parseFloat(heightValue);
    if (!heightNum || heightNum <= 0) {
      assessmentCrownAreaHint.textContent = 'Chybí výška stromu';
      return;
    }
    if (!widthNum || widthNum <= 0) {
      assessmentCrownAreaHint.textContent = 'Zadej šířku koruny';
      return;
    }
    assessmentCrownAreaHint.textContent = '';
  }

  function updateCrownAreaHintFromInputs() {
    const widthVal = assessmentCrownWidthInput ? assessmentCrownWidthInput.value : null;
    const heightVal = assessmentHeightInput ? assessmentHeightInput.value : null;
    const areaVal = assessmentCrownAreaInput ? assessmentCrownAreaInput.value : null;
    updateCrownAreaHint(areaVal, widthVal, heightVal);
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
    if (assessmentCrownWidthInput) assessmentCrownWidthInput.value = '';
    if (assessmentCrownAreaInput) assessmentCrownAreaInput.value = '';
    if (assessmentCrownAreaHint) assessmentCrownAreaHint.textContent = '';
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
    updateCrownAreaHintFromInputs();
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
        if (assessmentCrownWidthInput && data.crown_width_m != null) {
          assessmentCrownWidthInput.value = data.crown_width_m;
        }
        if (assessmentCrownAreaInput && data.crown_area_m2 != null) {
          assessmentCrownAreaInput.value = data.crown_area_m2;
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
        updateCrownAreaHintFromInputs();
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
      crown_width_m:
        assessmentCrownWidthInput && assessmentCrownWidthInput.value
          ? assessmentCrownWidthInput.value
          : null,
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

  function setInterventionDescriptionOpen(open) {
    if (!interventionDescriptionWrap || !interventionDescriptionToggle) return;
    interventionDescriptionWrap.classList.toggle('show', !!open);
    interventionDescriptionToggle.textContent = open ? 'Skrýt popis' : 'Přidat popis';
    if (open && interventionDescriptionInput) {
      interventionDescriptionInput.focus();
    }
  }

  function syncInterventionDescriptionVisibility() {
    const hasText =
      interventionDescriptionInput &&
      interventionDescriptionInput.value &&
      interventionDescriptionInput.value.trim();
    setInterventionDescriptionOpen(!!hasText);
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
    if (debugEnabled && items && items.length) {
      console.debug('map_ui interventions keys', Object.keys(items[0] || {}));
    }
    if (!items || !items.length) {
      interventionListContainer.innerHTML =
        '<p class="text-muted mb-1">Zatím nejsou zadány žádné zásahy.</p>';
      return;
    }
    const currentItems = items.filter(function (item) {
      return item.status_code === 'proposed' || item.status_code === 'done_pending_owner';
    });
    const historyItems = items.filter(function (item) {
      return item.status_code === 'completed';
    });

    function renderSection(list, isHistory) {
      let sectionHtml = '';
      if (isHistory) {
        sectionHtml += '<details class="mb-1">';
        sectionHtml +=
          '<summary class="small text-muted">Historie (' + list.length + ')</summary>';
      } else {
        sectionHtml += '<div class="mb-1"><strong>Aktuální zásahy</strong></div>';
      }

      if (!list.length) {
        if (!isHistory) {
          sectionHtml += '<p class="text-muted mb-1">Zatím nejsou zadány žádné zásahy.</p>';
        }
        if (isHistory) {
          sectionHtml += '</details>';
        }
        return sectionHtml;
      }

      sectionHtml += '<div><table class="table table-sm mb-1"><thead><tr>';
      sectionHtml +=
        '<th>Kód</th><th class="d-none d-sm-table-cell">Název</th><th>Stav</th><th class="d-none d-md-table-cell">Vytvořeno</th><th>Akce</th>';
      sectionHtml += '</tr></thead><tbody>';
      list.forEach(function (item) {
        const created = item.created_at || '';
        const handed = item.handed_over_for_check_at || null;
        const transitionUrl = item.transition_url || '';
        let label = '';
        if (handed) {
          label = 'Předáno ke kontrole';
        } else if (created) {
          label = 'Vytvořeno';
        }
        let statusBadge =
          '<span class="badge bg-light text-dark intervention-status-badge">' +
          (item.status || '') +
          '</span>';
        if (item.status_code === 'proposed') {
          statusBadge =
            '<span class="badge bg-secondary intervention-status-badge">Navrženo</span>';
        } else if (item.status_code === 'done_pending_owner') {
          statusBadge =
            '<span class="badge bg-warning text-dark intervention-status-badge">Hotovo – čeká na potvrzení</span>';
        } else if (item.status_code === 'completed') {
          statusBadge =
            '<span class="badge bg-success intervention-status-badge">Potvrzeno</span>';
        }
        sectionHtml += '<tr>';
        sectionHtml += '<td>' + (item.code || '');
        if (item.name) {
          sectionHtml += '<div class="text-muted small d-sm-none">' + item.name + '</div>';
        }
        if (item.status_note) {
          sectionHtml += '<div class="text-muted small">Pozn.: ' + item.status_note + '</div>';
        }
        sectionHtml += '</td>';
        sectionHtml += '<td class="d-none d-sm-table-cell">' + (item.name || '') + '</td>';
        sectionHtml += '<td>' + statusBadge + '</td>';
        sectionHtml += '<td class="d-none d-md-table-cell">';
        if (label || created || handed) {
          const ts = handed || created;
          sectionHtml += '<div class="small text-muted">';
          if (label) sectionHtml += label + ': ';
          sectionHtml += ts ? new Date(ts).toLocaleString('cs-CZ') : '-';
          sectionHtml += '</div>';
        } else {
          sectionHtml += '<span class="text-muted">-</span>';
        }
        sectionHtml += '</td>';
        sectionHtml +=
          '<td class="text-end"><div class="d-flex flex-wrap gap-1 justify-content-end interventions-actions">';
        const actions = item.allowed_actions || {};
        if (!isHistory && actions.mark_done) {
          sectionHtml +=
            '<button type="button" class="btn btn-outline-success btn-sm me-1 py-0 px-1 intervention-done-btn" data-action="transition" data-target="done_pending_owner" data-transition-url="' + transitionUrl + '" data-intervention-id="' +
            item.id +
            '" title="Označit hotovo"><i class="bi bi-check"></i></button>';
        }
        if (!isHistory && actions.confirm) {
          sectionHtml +=
            '<button type="button" class="btn btn-outline-primary btn-sm me-1 py-0 px-2" data-action="transition" data-target="completed" data-transition-url="' + transitionUrl + '" data-intervention-id="' +
            item.id +
            '">Potvrdit</button>';
        }
        if (!isHistory && actions.return) {
          sectionHtml +=
            '<button type="button" class="btn btn-outline-warning btn-sm py-0 px-2" data-action="transition" data-target="proposed" data-transition-url="' + transitionUrl + '" data-intervention-id="' +
            item.id +
            '">Vrátit</button>';
        }
        sectionHtml += '</div></td>';
        sectionHtml += '</tr>';
        if (item.description) {
          sectionHtml +=
            '<tr class="intervention-note-row"><td colspan="5">' +
            '<div class="text-muted small mt-1 intervention-note">' +
            item.description +
            '</div></td></tr>';
        }
      });
      sectionHtml += '</tbody></table></div>';
      if (isHistory) {
        sectionHtml += '</details>';
      }
      return sectionHtml;
    }

    let html = '';
    html += renderSection(currentItems, false);
    if (historyItems.length) {
      html += renderSection(historyItems, true);
    }
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

  function transitionIntervention(recordId, transitionUrl, target, note, buttonEl) {
    if (!transitionUrl) {
      setInterventionMessage('Nepodařilo se změnit stav zásahu.', true);
      return;
    }
    const payload = new URLSearchParams();
    payload.set('target', target);
    if (note) payload.set('note', note);
    if (buttonEl) buttonEl.disabled = true;
    const headers = {
      'X-Requested-With': 'XMLHttpRequest',
      'Content-Type': 'application/x-www-form-urlencoded',
    };
    if (cfg.csrfToken) headers['X-CSRFToken'] = cfg.csrfToken;
    fetch(transitionUrl, {
      method: 'POST',
      headers: headers,
      body: payload.toString(),
    })
        .then(function (resp) {
          if (!resp.ok) {
            return resp.text().then(function (text) {
              console.error('transition failed', { status: resp.status, body: text });
              setInterventionMessage('Nepodařilo se změnit stav zásahu.', true);
              throw new Error('transition failed');
            });
          }
          loadInterventionsForRecord(recordId);
          if (typeof window.refreshProjectWorkrecords === 'function') {
            window.refreshProjectWorkrecords();
          }
        })
      .catch(function () {
        setInterventionMessage('Nepodařilo se změnit stav zásahu.', true);
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
    syncInterventionDescriptionVisibility();
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
    payload.delete('due_date');
    payload.delete('assigned_to');
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
          syncInterventionDescriptionVisibility();
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
          if (!data.intervention.allowed_actions) {
            loadInterventionsForRecord(rid);
          }
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
    menuButton = document.getElementById('mapMenuButton');
    controlsPanel = document.getElementById('mapControlsPanel');
    projectTitle = document.getElementById('mapProjectTitle');
    workrecordPanelActions = document.getElementById('workrecord-panel-actions');
    moveLocationBanner = document.getElementById('moveLocationBanner');
    moveLocationCancelBtn = document.getElementById('moveLocationCancelBtn');
    moveLocationSaveBtn = document.getElementById('moveLocationSaveBtn');
    moveLocationMessage = document.getElementById('moveLocationMessage');
    const saveFab = document.getElementById('saveFab');
    if (cfg.disableLocationConfirmFab && saveFab) {
      saveFab.remove();
    }
    if (debugEnabled) {
      console.debug('map_ui dom', {
        bottomPanel: !!bottomPanel,
        treePanel: !!treePanel,
      });
    }
    updateProjectTitle();

    if (menuButton && controlsPanel) {
      menuButton.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        const isOpen = controlsPanel.classList.contains('open');
        setControlsOpen(!isOpen);
      });
      document.addEventListener('click', function (event) {
        if (!controlsPanel.classList.contains('open')) return;
        if (controlsPanel.contains(event.target) || menuButton.contains(event.target)) return;
        setControlsOpen(false);
      });
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          setControlsOpen(false);
        }
      });
    }

    if (treePanel) {
      treePanel.addEventListener('click', function (event) {
        if (event.target.closest('.tree-panel-close')) {
          event.preventDefault();
          closeTreePanel();
        }
      });
    }

    if (workrecordPanelActions) {
      workrecordPanelActions.addEventListener('click', function (event) {
        const btn = event.target.closest('[data-action="move-location"]');
        if (!btn) return;
        event.preventDefault();
        const recordId = btn.getAttribute('data-record-id');
        enterMoveLocationMode(recordId);
      });
    }

    if (moveLocationCancelBtn) {
      moveLocationCancelBtn.addEventListener('click', function () {
        cancelMoveLocationMode();
      });
    }
    if (moveLocationSaveBtn) {
      moveLocationSaveBtn.addEventListener('click', function () {
        submitMoveLocation();
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
    assessmentCrownWidthInput = document.getElementById('assessmentCrownWidth');
    assessmentCrownAreaInput = document.getElementById('assessmentCrownArea');
    assessmentCrownAreaHint = document.getElementById('assessmentCrownAreaHint');
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
    if (assessmentCrownWidthInput) {
      assessmentCrownWidthInput.addEventListener('input', updateCrownAreaHintFromInputs);
    }
    if (assessmentHeightInput) {
      assessmentHeightInput.addEventListener('input', updateCrownAreaHintFromInputs);
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
    interventionDescriptionWrap = document.getElementById('interventionDescriptionWrap');
    interventionDescriptionToggle = document.getElementById('interventionDescriptionToggle');
    interventionDescriptionInput = document.getElementById('id_description');
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
    if (interventionDescriptionToggle) {
      interventionDescriptionToggle.addEventListener('click', function () {
        const isOpen =
          interventionDescriptionWrap &&
          interventionDescriptionWrap.classList.contains('show');
        setInterventionDescriptionOpen(!isOpen);
      });
      setInterventionDescriptionOpen(false);
    }
    if (interventionListContainer) {
      interventionListContainer.addEventListener('click', function (e) {
        const btn = e.target.closest('[data-action="transition"]');
        if (!btn) return;
        const recordId = interventionTreeIdInput ? interventionTreeIdInput.value : null;
        const transitionUrl = btn.getAttribute('data-transition-url');
        const target = btn.getAttribute('data-target');
        if (!recordId || !transitionUrl || !target) return;
        let note = '';
        if (target === 'proposed') {
          note = window.prompt('Poznámka k vrácení');
          if (!note) return;
        }
        transitionIntervention(recordId, transitionUrl, target, note, btn);
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
    window.workTrackerMapUi = {
      isMoveLocationMode: function () {
        return moveLocationMode;
      },
      setPendingLngLat: setPendingMoveLocation,
      enterMoveLocationMode: enterMoveLocationMode,
      cancelMoveLocationMode: cancelMoveLocationMode,
    };
    updateMoveLocationBanner();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
