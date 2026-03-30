function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[char]));
}

function safeJsonParse(value, fallback) {
  try {
    return JSON.parse(value);
  } catch (error) {
    console.warn('JSON parse failed', error);
    return fallback;
  }
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function markerHtml(item) {
  const tags = Array.isArray(item.tags) ? item.tags.map(escapeHtml).join(' · ') : '';
  const salary = item.salary ? `<span>${escapeHtml(item.salary)}</span><br>` : '';
  return `
    <div style="min-width:220px; display:grid; gap:6px;">
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.company || '')}</span>
      ${salary}
      ${tags ? `<small>${tags}</small>` : ''}
      <a href="${escapeHtml(item.url || '#')}">Открыть карточку</a>
    </div>`;
}

function initCollectionMaps() {
  if (typeof L === 'undefined') return;

  document.querySelectorAll('[data-map-instance]').forEach(mapEl => {
    const payload = safeJsonParse(mapEl.dataset.map || '[]', []);
    const listRoot = mapEl.dataset.listSelector ? document.querySelector(mapEl.dataset.listSelector) : null;
    const countEl = mapEl.dataset.countSelector ? document.querySelector(mapEl.dataset.countSelector) : null;
    const map = L.map(mapEl).setView([55.7512, 37.6184], 10);

    mapEl._leafletMap = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const cluster = typeof L.markerClusterGroup === 'function'
      ? L.markerClusterGroup({ showCoverageOnHover: false, spiderfyOnMaxZoom: true })
      : L.layerGroup();

    const bounds = [];
    const markerMap = new Map();
    const cards = listRoot ? Array.from(listRoot.querySelectorAll('[data-map-card-id]')) : [];

    function syncViewportList() {
      if (!listRoot) return;
      const currentBounds = map.getBounds();
      let visible = 0;

      payload.forEach(item => {
        const card = listRoot.querySelector(`[data-map-card-id="${item.id}"]`);
        if (!card) return;
        const inside = Number.isFinite(item.lat) && Number.isFinite(item.lng)
          ? currentBounds.contains([item.lat, item.lng])
          : true;
        card.style.display = inside ? 'grid' : 'none';
        if (inside) visible += 1;
      });

      if (countEl) countEl.textContent = String(visible);
    }

    payload.forEach(item => {
      if (!Number.isFinite(item.lat) || !Number.isFinite(item.lng)) return;
      const color = item.color || cssVar('--primary', '#f2994a');
      const marker = L.circleMarker([item.lat, item.lng], {
        radius: 9,
        color,
        fillColor: color,
        fillOpacity: 0.9,
        weight: 2
      }).bindPopup(markerHtml(item));
      marker.on('mouseover', () => marker.openPopup());
      cluster.addLayer(marker);
      markerMap.set(String(item.id), marker);
      bounds.push([item.lat, item.lng]);
    });

    map.addLayer(cluster);
    if (bounds.length) {
      map.fitBounds(bounds, { padding: [30, 30] });
    }

    cards.forEach(card => {
      card.addEventListener('mouseenter', () => {
        const marker = markerMap.get(String(card.dataset.mapCardId));
        if (marker) marker.openPopup();
      });
    });

    map.on('moveend zoomend', syncViewportList);
    mapEl._syncViewportList = syncViewportList;

    setTimeout(() => {
      map.invalidateSize();
      syncViewportList();
    }, 50);
  });
}

function initTabs() {
  document.querySelectorAll('[data-tab-root]').forEach(root => {
    const buttons = Array.from(root.querySelectorAll('[data-tab-button]'));
    const panels = Array.from(root.querySelectorAll('[data-tab-panel]'));
    const hiddenInputs = Array.from(root.querySelectorAll('input[name="tab"]'));

    function setActive(tabName) {
      root.dataset.activeTab = tabName;
      hiddenInputs.forEach(input => {
        input.value = tabName;
      });

      buttons.forEach(button => {
        const isActive = button.dataset.tabButton === tabName;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-selected', String(isActive));
      });

      panels.forEach(panel => {
        panel.hidden = panel.dataset.tabPanel !== tabName;
      });

      const activePanel = panels.find(panel => panel.dataset.tabPanel === tabName);
      if (activePanel) {
        activePanel.querySelectorAll('[data-map-instance], [data-map-picker]').forEach(mapEl => {
          const map = mapEl._leafletMap;
          if (map) {
            setTimeout(() => {
              map.invalidateSize();
              if (typeof mapEl._syncViewportList === 'function') {
                mapEl._syncViewportList();
              }
            }, 80);
          }
        });
      }
    }

    buttons.forEach(button => {
      button.addEventListener('click', () => setActive(button.dataset.tabButton));
    });

    const defaultTab = root.dataset.activeTab || (buttons[0] && buttons[0].dataset.tabButton) || 'opportunities';
    setActive(defaultTab);
  });
}

function initMapPickers() {
  if (typeof L === 'undefined') return;

  document.querySelectorAll('[data-map-picker]').forEach(mapEl => {
    const latInput = document.querySelector(mapEl.dataset.latInput || '');
    const lngInput = document.querySelector(mapEl.dataset.lngInput || '');
    if (!latInput || !lngInput) return;

    const initialLat = parseFloat(latInput.value) || 55.7512;
    const initialLng = parseFloat(lngInput.value) || 37.6184;
    const statusEl = mapEl.parentElement.querySelector('[data-map-picker-status]');
    const map = L.map(mapEl, { scrollWheelZoom: false }).setView([initialLat, initialLng], 11);

    mapEl._leafletMap = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const marker = L.marker([initialLat, initialLng], { draggable: true }).addTo(map);

    function applyCoords(lat, lng, shouldPan = true) {
      const safeLat = Number.isFinite(lat) ? lat : 55.7512;
      const safeLng = Number.isFinite(lng) ? lng : 37.6184;
      latInput.value = safeLat.toFixed(6);
      lngInput.value = safeLng.toFixed(6);
      marker.setLatLng([safeLat, safeLng]);
      if (shouldPan) {
        map.panTo([safeLat, safeLng]);
      }
      if (statusEl) {
        statusEl.textContent = `Выбрана точка: ${safeLat.toFixed(6)}, ${safeLng.toFixed(6)}`;
      }
    }

    map.on('click', event => {
      applyCoords(event.latlng.lat, event.latlng.lng, true);
    });

    marker.on('dragend', () => {
      const point = marker.getLatLng();
      applyCoords(point.lat, point.lng, false);
    });

    [latInput, lngInput].forEach(input => {
      input.addEventListener('change', () => {
        applyCoords(parseFloat(latInput.value), parseFloat(lngInput.value));
      });
    });

    setTimeout(() => {
      map.invalidateSize();
      applyCoords(initialLat, initialLng, false);
    }, 50);
  });
}

function buildChartTheme() {
  return {
    foreground: cssVar('--text', '#1e1a16'),
    grid: 'rgba(146, 92, 32, 0.14)',
    primary: cssVar('--primary', '#f2994a'),
    success: cssVar('--success', '#2f9e5f'),
    purple: cssVar('--purple', '#8b5cf6'),
    blue: cssVar('--blue', '#3b82f6')
  };
}

function initRadarChart() {
  const el = document.getElementById('radarChart');
  if (!el || typeof Chart === 'undefined') return;
  const data = safeJsonParse(el.dataset.points || '[]', []);
  const theme = buildChartTheme();

  new Chart(el, {
    type: 'radar',
    data: {
      labels: ['Hard Skills', 'Data / DB', 'Soft Skills', 'Leadership'],
      datasets: [{
        label: 'Профиль',
        data,
        borderColor: theme.primary,
        backgroundColor: 'rgba(242, 153, 74, 0.16)',
        pointBackgroundColor: theme.primary,
        pointBorderColor: '#fff'
      }]
    },
    options: {
      responsive: true,
      scales: {
        r: {
          suggestedMin: 0,
          suggestedMax: 100,
          grid: { color: theme.grid },
          angleLines: { color: theme.grid },
          pointLabels: { color: theme.foreground },
          ticks: { display: false }
        }
      },
      plugins: { legend: { labels: { color: theme.foreground } } }
    }
  });
}

function initAnalyticsCharts() {
  const typeEl = document.getElementById('typeChart');
  const theme = buildChartTheme();

  if (typeEl && typeof Chart !== 'undefined') {
    const series = safeJsonParse(typeEl.dataset.series || '{}', {});
    new Chart(typeEl, {
      type: 'doughnut',
      data: {
        labels: Object.keys(series),
        datasets: [{
          data: Object.values(series),
          backgroundColor: [theme.primary, theme.success, theme.purple, theme.blue]
        }]
      },
      options: { plugins: { legend: { labels: { color: theme.foreground } } } }
    });
  }

  const skillsEl = document.getElementById('skillsChart');
  if (skillsEl && typeof Chart !== 'undefined') {
    const series = safeJsonParse(skillsEl.dataset.series || '{}', {});
    new Chart(skillsEl, {
      type: 'bar',
      data: {
        labels: Object.keys(series),
        datasets: [{
          label: 'Частота',
          data: Object.values(series),
          backgroundColor: 'rgba(242, 153, 74, 0.72)',
          borderColor: theme.primary,
          borderWidth: 1,
          borderRadius: 10
        }]
      },
      options: {
        scales: {
          x: { ticks: { color: theme.foreground }, grid: { color: theme.grid } },
          y: { ticks: { color: theme.foreground }, grid: { color: theme.grid } }
        },
        plugins: { legend: { labels: { color: theme.foreground } } }
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initCollectionMaps();
  initMapPickers();
  initTabs();
  initRadarChart();
  initAnalyticsCharts();
});
