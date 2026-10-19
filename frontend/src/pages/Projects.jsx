import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useNotify } from '../context/NotificationContext';
import { useLoading } from '../context/LoadingContext';
import { useConfirm } from '../context/ConfirmContext';
import { api, apiCache } from '../api';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';

export default function Projects() {
  const navigate = useNavigate();
  const notify = useNotify();
  const loadingCtrl = useLoading();
  const confirm = useConfirm();

  const [projects, setProjects] = useState(() => apiCache.get('/projects') || []);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(() => !apiCache.get('/projects'));

  const load = useCallback(async () => {
    try {
      const res = await api.get('/projects');
      setProjects(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const deleteProject = async (id, name) => {
    const ok = await confirm(`Delete project "${name}"? This cannot be undone.`);
    if (!ok) return;
    try {
      loadingCtrl.start();
      await api.del(`/projects/${id}`);
      notify({ type: 'success', message: 'Project deleted' });
      load();
    } catch (e) {
      notify({ type: 'error', message: e.message });
    } finally {
      loadingCtrl.stop();
    }
  };

  if (error) return <div className="p-8 text-red-600">{error}</div>;
  if (loading) return <div className="p-8 text-gray-400">Loading…</div>;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <Button as={Link} to="/projects/new" variant="default">New Project</Button>
      </div>

      {projects.length === 0 && (
        <Card className="p-8 text-center">
          <svg className="w-16 h-16 mx-auto text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2h14m0 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2h14z" /></svg>
          <h3 className="mt-4 text-lg font-medium text-gray-900">No projects yet</h3>
          <p className="mt-2 text-gray-500">Create your first project to start organizing outreach</p>
          <Button as={Link} to="/projects/new" className="mt-4">Create Project</Button>
        </Card>
      )}

      {projects.length > 0 && (
        <Card className="overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Groups</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Leads</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {projects.map(p => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <Link to={`/projects/${p.id}`} className="text-teal-500 hover:underline font-medium">{p.name}</Link>
                    {p.description && <p className="text-sm text-gray-500 mt-1 truncate max-w-xs">{p.description}</p>}
                  </td>
                  <td className="px-6 py-4 text-gray-600">{p.contact_group_count || 0}</td>
                  <td className="px-6 py-4 text-gray-600">{p.lead_count || 0}</td>
                  <td className="px-6 py-4">
                    {p.paused ? (
                      <span className="inline-block px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-700">Paused</span>
                    ) : (
                      <span className="inline-block px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-700">Active</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-500 text-sm">
                    {p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link to={`/projects/${p.id}`}>
                        <Button variant="outline" size="sm">Open</Button>
                      </Link>
                      <Button variant="outline" size="sm" onClick={() => deleteProject(p.id, p.name)}>Delete</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}