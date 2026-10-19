import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNotify } from '../context/NotificationContext';
import { useLoading } from '../context/LoadingContext';
import { useConfirm } from '../context/ConfirmContext';
import { api, apiCache } from '../api';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import {
  formatDateKey,
  formatTimeKey,
  formatDateTimeKey,
  normalizeTimeZone,
} from '../utils/datetime';

const STATUS_LABELS = {
  pending: 'Upcoming',
  due: 'Due Now',
  sent: 'Sent',
  skipped: 'Skipped',
  blocked: 'Blocked',
};

const STATUS_COLORS = {
  pending: 'bg-blue-100 text-blue-700',
  due: 'bg-orange-100 text-orange-700',
  sent: 'bg-green-100 text-green-700',
  skipped: 'bg-gray-100 text-gray-600',
  blocked: 'bg-red-100 text-red-700',
};

const CHANNEL_LABELS = {
  email: 'Email',
  linkedin_dm: 'LinkedIn DM',
};

const CHANNEL_COLORS = {
  email: 'bg-blue-100 text-blue-700',
  linkedin_dm: 'bg-blue-100 text-blue-700',
};

export default function OutreachQueue() {
  const navigate = useNavigate();
  const notify = useNotify();
  const loadingCtrl = useLoading();
  const confirm = useConfirm();

  const [drafts, setDrafts] = useState(() => apiCache.get('/templates/drafts') || []);
  const [projects, setProjects] = useState(() => apiCache.get('/projects') || []);
  const [sequences, setSequences] = useState(() => apiCache.get('/templates/sequences') || []);
  const [leads, setLeads] = useState(() => apiCache.get('/leads') || []);
  const [loading, setLoading] = useState(() => !apiCache.get('/templates/drafts'));
  const [error, setError] = useState(null);

  const [filters, setFilters] = useState({
    project: 'all',
    group: 'all',
    contact: 'all',
    channel: 'all',
    sequence: 'all',
    status: 'all',
    dateFrom: '',
    dateTo: '',
  });
  const [sortConfig, setSortConfig] = useState({ key: 'due_at', direction: 'asc' });
  const [pagination, setPagination] = useState({ page: 1, pageSize: 25, total: 0 });
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);

  const loadDrafts = useCallback(async () => {
    loadingCtrl.start();
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value && value !== 'all') params.append(key, value);
      });
      params.append('page', pagination.page);
      params.append('page_size', pagination.pageSize);
      params.append('sort', sortConfig.key);
      params.append('direction', sortConfig.direction);

      const res = await api.get(`/templates/drafts?${params.toString()}`);
      setDrafts(res.items || res);
      setPagination(prev => ({ ...prev, total: res.total || res.items?.length || 0 }));
    } catch (e) {
      setError(e.message);
      notify({ type: 'error', message: 'Failed to load drafts' });
    } finally {
      loadingCtrl.stop();
      setLoading(false);
    }
  }, [filters, pagination.page, pagination.pageSize, sortConfig]);

  useEffect(() => {
    loadDrafts();
  }, [loadDrafts]);

  useEffect(() => {
    api.get('/projects').then(setProjects).catch(() => {});
    api.get('/templates/sequences').then(setSequences).catch(() => {});
    api.get('/leads').then(setLeads).catch(() => {});
  }, []);

  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  const handlePageChange = (page) => {
    setPagination(prev => ({ ...prev, page }));
  };

  const handlePageSizeChange = (pageSize) => {
    setPagination(prev => ({ ...prev, pageSize, page: 1 }));
  };

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setPagination(prev => ({ ...prev, page: 1 }));
  };

  const openDetail = (draft) => {
    setSelectedDraft(draft);
    setDetailModalOpen(true);
  };

  const closeDetail = () => {
    setDetailModalOpen(false);
    setSelectedDraft(null);
  };

  const copyToClipboard = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text);
      notify({ type: 'success', message: `${label} copied to clipboard` });
    } catch {
      notify({ type: 'error', message: `Failed to copy ${label}` });
    }
  };

  const handleMarkSent = async (draft) => {
    const ok = await confirm(`Mark this ${CHANNEL_LABELS[draft.channel]} as sent?`);
    if (!ok) return;

    try {
      loadingCtrl.start();
      await api.patch(`/templates/drafts/${draft.id}`, {
        status: 'sent',
        sent_at: new Date().toISOString(),
      });
      notify({ type: 'success', message: 'Marked as sent' });
      loadDrafts();
    } catch (e) {
      notify({ type: 'error', message: e.message });
    } finally {
      loadingCtrl.stop();
    }
  };

  const handleSkip = async (draft) => {
    const ok = await confirm(`Skip this ${CHANNEL_LABELS[draft.channel]}? The contact will not receive this message.`);
    if (!ok) return;

    try {
      loadingCtrl.start();
      await api.patch(`/templates/drafts/${draft.id}`, { status: 'skipped' });
      notify({ type: 'success', message: 'Message skipped' });
      loadDrafts();
    } catch (e) {
      notify({ type: 'error', message: e.message });
    } finally {
      loadingCtrl.stop();
    }
  };

  const handleStopSequence = async (draft) => {
    const ok = await confirm(`Stop the remaining sequence for this contact? All future steps will be skipped.`);
    if (!ok) return;

    try {
      loadingCtrl.start();
      await api.patch(`/templates/drafts/${draft.id}/stop-sequence`);
      notify({ type: 'success', message: 'Sequence stopped for this contact' });
      loadDrafts();
    } catch (e) {
      notify({ type: 'error', message: e.message });
    } finally {
      loadingCtrl.stop();
    }
  };

  const openLinkedInProfile = (url) => {
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  const formatDueDate = (dateStr) => {
    if (!dateStr) return '—';
    const tz = normalizeTimeZone(selectedDraft?.project_timezone);
    return formatDateTimeKey(dateStr, tz);
  };

  const formatDueDateShort = (dateStr) => {
    if (!dateStr) return '—';
    const tz = normalizeTimeZone(selectedDraft?.project_timezone);
    return formatDateTimeKey(dateStr, tz, true);
  };

  const getProject = (projectId) => projects.find(p => p.id === projectId);
  const getSequence = (sequenceId) => sequences.find(s => s.id === sequenceId);
  const getLead = (leadId) => leads.find(l => l.id === leadId);

  const statusOrder = { due: 0, pending: 1, sent: 2, skipped: 3, blocked: 4 };

  const sortedDrafts = useMemo(() => {
    return [...drafts].sort((a, b) => {
      const statusA = statusOrder[a.status] ?? 99;
      const statusB = statusOrder[b.status] ?? 99;
      if (statusA !== statusB) return statusA - statusB;
      if (a.due_at && b.due_at) return new Date(a.due_at) - new Date(b.due_at);
      return 0;
    });
  }, [drafts]);

  const groupedDrafts = useMemo(() => {
    const groups = { due: [], pending: [], sent: [], skipped: [], blocked: [] };
    sortedDrafts.forEach(d => groups[d.status]?.push(d));
    return groups;
  }, [sortedDrafts]);

  if (error) return <div className="p-8 text-red-600">{error}</div>;
  if (loading && !drafts.length) return <div className="p-8 text-gray-400">Loading…</div>;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <div className="flex flex-col gap-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">Outreach Queue</h1>
            <p className="text-gray-500 mt-1">Manage your manual outreach drafts</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => loadDrafts()} disabled={loading}>
              <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
              Refresh
            </Button>
          </div>
        </div>

        {/* Filters */}
        <Card className="p-4">
          <div className="flex flex-wrap gap-4">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">Project</label>
              <select
                value={filters.project}
                onChange={(e) => handleFilterChange('project', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Projects</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>

            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">Contact</label>
              <select
                value={filters.contact}
                onChange={(e) => handleFilterChange('contact', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Contacts</option>
                {leads.map(l => <option key={l.id} value={l.id}>{l.email || l.name || l.id}</option>)}
              </select>
            </div>

            <div className="flex-1 min-w-[160px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">Channel</label>
              <select
                value={filters.channel}
                onChange={(e) => handleFilterChange('channel', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Channels</option>
                <option value="email">Email</option>
                <option value="linkedin_dm">LinkedIn DM</option>
              </select>
            </div>

            <div className="flex-1 min-w-[160px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select
                value={filters.status}
                onChange={(e) => handleFilterChange('status', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Statuses</option>
                <option value="due">Due Now</option>
                <option value="pending">Upcoming</option>
                <option value="sent">Sent</option>
                <option value="skipped">Skipped</option>
                <option value="blocked">Blocked</option>
              </select>
            </div>

            <div className="flex-1 min-w-[160px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">From Date</label>
              <input
                type="date"
                value={filters.dateFrom}
                onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="flex-1 min-w-[160px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">To Date</label>
              <input
                type="date"
                value={filters.dateTo}
                onChange={(e) => handleFilterChange('dateTo', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {Object.values(filters).some(v => v && v !== 'all') && (
              <div className="flex items-end">
                <Button variant="outline" size="sm" onClick={() => setFilters({
                  project: 'all', group: 'all', contact: 'all',
                  channel: 'all', sequence: 'all', status: 'all',
                  dateFrom: '', dateTo: '',
                })}>
                  Clear Filters
                </Button>
              </div>
            )}
          </div>
        </Card>

        {/* Queue Sections */}
        <div className="space-y-6">
          {Object.entries(STATUS_LABELS).map(([status, label]) => {
            const items = groupedDrafts[status] || [];
            if (!items.length) return null;

            return (
              <section key={status} className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status]}`}>
                      {label}
                    </span>
                    <span className="text-sm text-gray-500">({items.length})</span>
                  </div>
                </div>
              </section>
            );
          })}
        </div>

        {/* Pagination */}
        {pagination.total > pagination.pageSize && (
          <div className="flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handlePageChange(pagination.page - 1)}
              disabled={pagination.page === 1}
            >
              Previous
            </Button>
            <span className="text-sm text-gray-600">
              Page {pagination.page} of {Math.ceil(pagination.total / pagination.pageSize)}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handlePageChange(pagination.page + 1)}
              disabled={pagination.page >= Math.ceil(pagination.total / pagination.pageSize)}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}