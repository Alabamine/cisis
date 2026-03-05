// frontend/dashboard.js - ИСПРАВЛЕННАЯ ВЕРСИЯ

// Конфигурация API - ЭТО ГЛАВНОЕ!
const API_BASE = '/workspace/analytics/api';

let currentFilters = {
    days: 30,
    lab_id: 0
};

// Хранилище для графиков
let charts = {};

// Загрузка при старте
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ DOM загружен');
    console.log('🔧 API Base:', API_BASE);
    
    // Текущие фильтры
    currentFilters = {
        days: 30,
        lab_id: 0
    };
    
    // Загружаем список лабораторий
    loadLaboratories();
    
    // Загружаем все данные
    loadKPI();
    loadMonthlyLabor();
    loadLabDistribution();
    loadStatusDistribution();
    loadDailyRegistrations();
    loadEmployeeStats(); 
    
    // Кнопка обновления
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            console.log('🔄 Обновление данных...');
            refreshAllCharts();
        });
    }
    
    // Обработчик изменения периода
    const periodSelect = document.getElementById('period-select');
    if (periodSelect) {
        periodSelect.value = '30';
        periodSelect.addEventListener('change', function(e) {
            currentFilters.days = parseInt(e.target.value);
            console.log('📅 Период изменен:', currentFilters.days);
            refreshAllCharts();
        });
    }
    
    // Время обновления
    updateLastUpdateTime();
});

// Функция обновления всех графиков
function refreshAllCharts() {
    console.log('🔄 Обновление всех данных');
    loadKPI();
    loadMonthlyLabor();
    loadLabDistribution();
    loadStatusDistribution();
    loadEmployeeStats(); 
    loadDailyRegistrations();
    updateLastUpdateTime();
}

function updateLastUpdateTime() {
    const now = new Date();
    const el = document.getElementById('last-update');
    if (el) {
        el.innerHTML = `<i class="far fa-clock"></i> Обновлено: ${now.toLocaleString('ru-RU')}`;
    }
}

// ========== ЗАГРУЗКА ЛАБОРАТОРИЙ ==========
async function loadLaboratories() {
    try {
        const url = `${API_BASE}/laboratories`;
        console.log('📡 Запрос лабораторий:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const labs = await response.json();
        console.log('🏛️ Лаборатории:', labs);
        
        const select = document.getElementById('lab-select');
        if (!select) return;
        
        select.innerHTML = '<option value="0">Все лаборатории</option>';
        
        labs.forEach(lab => {
            if (lab.id !== 0) {
                const option = document.createElement('option');
                option.value = lab.id;
                option.textContent = lab.name;
                select.appendChild(option);
            }
        });
        
        // Обработчик изменения лаборатории
        select.addEventListener('change', function(e) {
            currentFilters.lab_id = parseInt(e.target.value);
            console.log('🏛️ Лаборатория изменена:', currentFilters.lab_id);
            refreshAllCharts();
        });
        
    } catch (error) {
        console.error('❌ Ошибка загрузки лабораторий:', error);
        const select = document.getElementById('lab-select');
        if (select) {
            select.innerHTML = '<option value="0">Все лаборатории</option>';
        }
    }
}

// ========== KPI ==========
async function loadKPI() {
    console.log('📊 Загрузка KPI...');
    
    try {
        const url = `${API_BASE}/kpi?lab_id=${currentFilters.lab_id}`;
        console.log('📡 Запрос KPI:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        console.log('📊 Данные KPI:', data);
        
        const kpiGrid = document.getElementById('kpi-cards');
        if (!kpiGrid) return;
        
        kpiGrid.innerHTML = `
            <div class="kpi-card" style="background: #e4f4fc;">
                <div class="kpi-label">Всего образцов</div>
                <div class="kpi-value">${data.total_samples || 0}</div>
            </div>
            <div class="kpi-card" style="background: #d6f7cf;">
                <div class="kpi-label">Активные</div>
                <div class="kpi-value">${data.active_samples || 0}</div>
            </div>
            <div class="kpi-card" style="background: #fccec3;">
                <div class="kpi-label">Просрочено</div>
                <div class="kpi-value">${data.overdue_samples || 0}</div>
            </div>
            <div class="kpi-card" style="background: #f8d7da;">
                <div class="kpi-label">Отменено</div>
                <div class="kpi-value">${data.cancelled_samples || 0}</div>
            </div>
            <div class="kpi-card" style="background: #fcfbc3;">
                <div class="kpi-label">Среднее время (дни)</div>
                <div class="kpi-value">${data.avg_test_days || 0}</div>
            </div>
            <div class="kpi-card" style="background: #efd7f7;">
                <div class="kpi-label">Количество сотрудников</div>
                <div class="kpi-value">${data.total_employees || 0}</div>
            </div>
        `;
        
    } catch (error) {
        console.error('❌ Ошибка KPI:', error);
    }
}

// ========== ГРАФИК ПО МЕСЯЦАМ ==========
async function loadMonthlyLabor() {
    console.log('📈 Загрузка графика по месяцам...');
    
    try {
        const url = `${API_BASE}/monthly-labor?lab_id=${currentFilters.lab_id}`;
        console.log('📡 Запрос monthly:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        console.log('📊 Данные monthly:', data);
        
        const canvas = document.getElementById('monthlyChart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        if (charts.monthly) charts.monthly.destroy();
        
        if (!data || data.length === 0) {
            canvas.parentElement.innerHTML = '<div style="padding: 50px; text-align: center;">Нет данных</div>';
            return;
        }
        
        charts.monthly = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(item => item.month),
                datasets: [{
                    label: 'Количество образцов',
                    data: data.map(item => item.samples_count),
                    backgroundColor: '#477cb6',
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
        
    } catch (error) {
        console.error('❌ Ошибка monthly:', error);
    }
}

// ========== ГРАФИК ЛАБОРАТОРИЙ ==========
async function loadLabDistribution() {
    console.log('🥧 Загрузка лабораторий...');
    
    try {
        const url = `${API_BASE}/laboratory-distribution`;
        console.log('📡 Запрос lab:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        console.log('🏛️ Данные лабораторий:', data);
        
        const canvas = document.getElementById('labChart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        if (charts.lab) charts.lab.destroy();
        
        if (!data || data.length === 0) return;
        
        charts.lab = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: data.map(item => item.laboratory),
                datasets: [{
                    data: data.map(item => item.samples_count),
                    backgroundColor: ['#007bff', '#28a745', '#ffc107', '#17a2b8', '#dc3545', '#6c757d']
                }]
            }
        });
        
    } catch (error) {
        console.error('❌ Ошибка лабораторий:', error);
    }
}

// ========== ГРАФИК СТАТУСОВ ==========
async function loadStatusDistribution() {
    console.log('🍩 Загрузка статусов...');
    
    try {
        const url = `${API_BASE}/status-distribution?lab_id=${currentFilters.lab_id}`;
        console.log('📡 Запрос status:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        console.log('📊 Данные статусов:', data);
        
        const canvas = document.getElementById('statusChart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        if (charts.status) charts.status.destroy();
        
        if (!data || data.length === 0) return;
        
        charts.status = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.map(item => item.status),
                datasets: [{
                    data: data.map(item => item.count),
                    backgroundColor: ['#007bff', '#ffc107', '#28a745', '#17a2b8', '#dc3545', '#6c757d']
                }]
            }
        });
        
    } catch (error) {
        console.error('❌ Ошибка статусов:', error);
    }
}


// ========== ТАБЛИЦА СОТРУДНИКОВ ==========
let employeeData = [];
let currentSort = {
    column: 'samples_tested',
    direction: 'desc'
};

async function loadEmployeeStats() {
    console.log('👥 Загрузка статистики сотрудников...');
    
    try {
        const url = `${API_BASE}/employee-stats?lab_id=${currentFilters.lab_id}`;
        console.log('📡 Запрос сотрудников:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        employeeData = await response.json();
        console.log('📊 Данные сотрудников:', employeeData);
        
        displayEmployeeTable();
        
    } catch (error) {
        console.error('❌ Ошибка загрузки сотрудников:', error);
        const tbody = document.getElementById('employees-tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #dc3545; padding: 30px;">Ошибка загрузки данных</td></tr>';
        }
    }
}

// ========== ГРАФИК ДИНАМИКИ РЕГИСТРАЦИЙ ПО ДНЯМ ==========
async function loadDailyRegistrations() {
    console.log('📈 Загрузка динамики регистраций по дням...');
    console.log('🔍 Текущие фильтры:', currentFilters);
    
    try {
        // Убираем days из URL, оставляем только lab_id
        const url = `${API_BASE}/daily-registrations?lab_id=${currentFilters.lab_id}`;
        console.log('📡 Запрос daily:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        console.log('📊 Данные daily:', data);
        
        const canvas = document.getElementById('trendChart');
        if (!canvas) {
            console.error('❌ Canvas trendChart не найден');
            return;
        }
        
        const ctx = canvas.getContext('2d');
        
        // Удаляем старый график
        if (charts.trend) charts.trend.destroy();
        
        // Если данных нет
        if (!data || data.length === 0) {
            canvas.style.display = 'none';
            const parent = canvas.parentElement;
            parent.innerHTML = '<div style="padding: 50px; text-align: center; color: #666;">Нет данных за выбранный период</div>';
            return;
        }
        
        canvas.style.display = 'block';
        
        // Создаем линейный график
        charts.trend = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.map(item => {
                    const date = new Date(item.date);
                    return date.toLocaleDateString('ru-RU', { 
                        day: '2-digit', 
                        month: '2-digit'
                    });
                }),
                datasets: [{
                    label: 'Количество регистраций',
                    data: data.map(item => item.registrations),
                    borderColor: '#477cb6',
                    backgroundColor: 'rgba(71, 124, 182, 0.1)',
                    borderWidth: 2,
                    pointBackgroundColor: '#477cb6',
                    pointBorderColor: 'white',
                    pointBorderWidth: 2,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    tension: 0.2,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `Регистраций: ${context.raw}`;
                            },
                            title: function(context) {
                                const date = new Date(data[context[0].dataIndex].date);
                                return date.toLocaleDateString('ru-RU');
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: currentFilters.lab_id !== 0 
                            ? 'Динамика регистраций (выбрана лаборатория)' 
                            : 'Динамика регистраций (все время)'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Количество образцов'
                        },
                        ticks: {
                            stepSize: 1,
                            precision: 0
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Дата'
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                            maxTicksLimit: 20
                        }
                    }
                }
            }
        });

        canvas.style.height = '280px';
        canvas.style.width = '100%';
        
        console.log('✅ График динамики создан');
        
    } catch (error) {
        console.error('❌ Ошибка загрузки daily registrations:', error);
        showError('trendChart');
    }
}

function displayEmployeeTable() {
    const tbody = document.getElementById('employees-tbody');
    if (!tbody) return;
    
    if (!employeeData || employeeData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 30px;">Нет данных о сотрудниках</td></tr>';
        return;
    }
    
    // Сортируем данные
    const sortedData = [...employeeData].sort((a, b) => {
        let valA, valB;
        
        if (currentSort.column === 'samples_tested') {
            valA = a.samples_tested || 0;
            valB = b.samples_tested || 0;
        } else {
            valA = a.protocols_made || 0;
            valB = b.protocols_made || 0;
        }
        
        return currentSort.direction === 'asc' ? valA - valB : valB - valA;
    });
    
    updateSortIcons();
    
    let html = '';
    sortedData.forEach(emp => {
        const fullName = `${emp.last_name || ''} ${emp.first_name || ''}`.trim() || 'Не указано';
        
        html += `
            <tr>
                <td><strong>${fullName}</strong></td>
                <td>${emp.role || 'Не указана'}</td>
                <td>${emp.laboratory_name || 'Не указана'}</td>
                <td class="text-center">${emp.samples_tested || 0}</td>
                <td class="text-center">${emp.protocols_made || 0}</td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

function updateSortIcons() {
    document.querySelectorAll('.sortable').forEach(th => {
        const sortType = th.dataset.sort;
        th.classList.remove('asc', 'desc');
        
        const icon = th.querySelector('.sort-icon');
        if (icon) {
            if (sortType === currentSort.column) {
                th.classList.add(currentSort.direction);
                icon.textContent = currentSort.direction === 'asc' ? '↑' : '↓';
            } else {
                icon.textContent = '↕️';
            }
        }
    });
}

function initSorting() {
    document.querySelectorAll('.sortable').forEach(th => {
        th.addEventListener('click', function() {
            const sortColumn = this.dataset.sort;
            
            if (currentSort.column === sortColumn) {
                currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                currentSort.column = sortColumn;
                currentSort.direction = 'desc';
            }
            
            displayEmployeeTable();
        });
    });
}

// ========== ПОКАЗАТЬ ОШИБКУ ==========
function showError(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (canvas && canvas.parentNode) {
        canvas.style.display = 'none';
        const parent = canvas.parentNode;
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = 'padding: 20px; text-align: center; color: #dc3545;';
        errorDiv.innerHTML = '❌ Ошибка загрузки';
        parent.appendChild(errorDiv);
    }
}