import { useState, useEffect, useCallback } from 'react';
import { useNotify } from '../context/NotificationContext';
import { useLoading } from '../context/LoadingContext';
import { useConfirm } from '../context/ConfirmContext';
import { api, apiCache } from '../api';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { FileUploadArea } from '../components/ui/FileUploadArea';

const CHANNEL_LABELS = {
  email: 'Email',
  linkedin_dm: 'LinkedIn DM',
};

const CHANNEL_COLORS = {
  email: 'bg-blue-100 text-blue-700',
  linkedin_dm: 'bg-blue-100 text-blue-700',
};

export default function Templates() {
  const notify = useNotify();
  const loadingCtrl = useLoading();
  const confirm = useConfirm();

  const [templates, setTemplates] = useState(() => apiCache.get('/templates') || []);
  const [loading, setLoading] = useState(() => !apiCache.get('/templates'));
  const [activeTab, setActiveTab] = useState('list');
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [previewData, setPreviewData] = useState(null);

  const [formData, setFormData] = useState({
    name: '',
    channel: 'email',
    subject: '',
    body: '',
    is_html: true,
    description: '',
  });

  const loadTemplates = useCallback(async () => {
    try {
      const res = await api.get('/templates');
      setTemplates(res);
    } catch (e) {
      notify({ type: 'error', message: 'Failed to load templates' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      loadingCtrl.start();
      if (editingTemplate) {
        await api.patch(`/templates/${editingTemplate.id}`, formData);
        notify({ type: 'success', message: 'Template updated' });
      } else {
        await api.post('/templates', formData);
        notify({ type: 'success', message: 'Template created' });
      }
      setEditingTemplate(null);
      setFormData({ name: '', channel: 'email', subject: '', body: '', is_html: true, description: '' });
      loadTemplates();
    } catch (e) {
      notify({ type: 'error', message: e.message });
    } finally {
      loadingCtrl.stop();
    }
  };

  const handleEdit = (template) => {
    setEditingTemplate(template);
    setFormData({
      name: template.name,
      channel: template.channel,
      subject: template.subject || '',
      body: template.body,
      is_html: template.is_html,
      description: template.description || '',
    });
    setActiveTab('editor');
  };

  const handleDelete = async (id) => {
    const ok = await confirm('Delete this template?');
    if (!ok) return;
    try {
      loadingCtrl.start();
      await api.del(`/templates/${id}`);
      notify({ type: 'success', message: 'Template deleted' });
      loadTemplates();
    } catch (e) {
      notify({ type: 'error', message: e.message });
    } finally {
      loadingCtrl.stop();
    }
  };

  const handleNew = () => {
    setEditingTemplate(null);
    setFormData({ name: '', channel: 'email', subject: '', body: '', is_html: true, description: '' });
    setActiveTab('editor');
  };

  const handleChannelChange = (channel) => {
    setFormData(prev => ({ ...prev, channel }));
  };

  const handlePreview = async () => {
    if (!formData.name) {
      notify({ type: 'error', message: 'Save template first to preview' });
      return;
    }
    // For preview, we need a lead ID. Let's fetch a sample lead.
    try {
      const leads = await api.get('/leads?limit=1');
      if (leads.length === 0) {
        notify({ type: 'error', message: 'No contacts available for preview' });
        return;
      }
      const res = await api.post('/templates/preview', {
        template_id: editingTemplate?.id || 0,
        lead_id: leads[0].id,
      });
      setPreviewData(res);
    } catch (e) {
      notify({ type: 'error', message: e.message });
    }
  };

  const copyToClipboard = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text);
      notify({ type: 'success', message: `${label} copied` });
    } catch {
      notify({ type: 'error', message: `Failed to copy ${label}` });
    }
  };

  if (loading) return <div className="p-8 text-gray-400">Loading…</div>;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <div className="flex flex-col gap-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">Templates</h1>
            <p className="text-gray-500 mt-1">Create and manage reusable email and LinkedIn DM templates</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => loadTemplates()} disabled={loading}>
              <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
              Refresh
            </Button>
            <Button onClick={handleNew}>New Template</Button>
          </div>
        </div>

        {activeTab === 'editor' && (
          <Card className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">{editingTemplate ? 'Edit Template' : 'New Template'}</h2>
              <Button variant="outline" onClick={() => { setEditingTemplate(null); setActiveTab('list'); }}>Cancel</Button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6 max-w-3xl">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                  <input
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Welcome Email"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Channel</label>
                  <select
                    value={formData.channel}
                    onChange={(e) => handleChannelChange(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="email">Email</option>
                    <option value="linkedin_dm">LinkedIn DM</option>
                  </select>
                </div>
              </div>

              {formData.channel === 'email' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
                  <input
                    type="text"
                    required
                    value={formData.subject}
                    onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Hello {{first_name}}, welcome to {{company}}"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Body {formData.channel === 'email' && formData.is_html && '(HTML)'}
                </label>
                <textarea
                  required
                  rows={12}
                  value={formData.body}
                  onChange={(e) => setFormData({ ...formData, body: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder={formData.channel === 'email'
                    ? 'Hi {{first_name}},\n\nThanks for joining {{company}}!'
                    : 'Hi {{first_name}}, thanks for connecting!'}
                />
              </div>

              {formData.channel === 'email' && (
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="is_html"
                    checked={formData.is_html}
                    onChange={(e) => setFormData({ ...formData, is_html: e.target.checked })}
                    className="rounded"
                  />
                  <label htmlFor="is_html" className="text-sm text-gray-700">HTML format</label>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  rows={3}
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Optional description for this template"
                />
              </div>

              <div className="flex gap-3 pt-4 border-t border-gray-200">
                <Button type="submit" disabled={loadingCtrl.loading}>
                  {loadingCtrl.loading ? 'Saving…' : (editingTemplate ? 'Update' : 'Create')} Template
                </Button>
                {editingTemplate && (
                  <Button variant="outline" onClick={() => { setEditingTemplate(null); setActiveTab('list'); }}>Cancel</Button>
                )}
              </div>
            </form>

            {previewData && (
              <div className="mt-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
                <h3 className="font-semibold mb-2">Preview (using sample contact)</h3>
                {previewData.subject && (
                  <div className="mb-2">
                    <span className="font-semibold text-gray-700">Subject: </span>
                    <span className="text-gray-900">{previewData.subject}</span>
                  </div>
                )}
                <div className="bg-white p-4 rounded border border-gray-200 whitespace-pre-wrap font-mono text-sm max-h-64 overflow-auto">
                  {previewData.body}
                </div>
                {previewData.missing_fields?.length > 0 && (
                  <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-yellow-800 text-sm">
                    <strong>Missing fields:</strong> {previewData.missing_fields.join(', ')}
                  </div>
                )}
              </div>
            )}
          </Card>
        )}

        {activeTab === 'list' && (
          <div className="space-y-4">
            {templates.length === 0 ? (
              <Card className="p-8 text-center">
                <svg className="w-12 h-12 mx-auto text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" /></svg>
                <h3 className="mt-4 text-lg font-medium text-gray-900">No templates yet</h3>
                <p className="mt-2 text-gray-500">Create your first email or LinkedIn DM template</p>
                <Button className="mt-4" onClick={handleNew}>Create Template</Button>
              </Card>
            ) : (
              <Card className="overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Channel</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Subject</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Updated</th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-32">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {templates.map(t => (
                      <tr key={t.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4 font-medium text-gray-900">{t.name}</td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${CHANNEL_COLORS[t.channel]}`}>
                            {CHANNEL_LABELS[t.channel] || t.channel}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-gray-500 max-w-xs truncate">
                          {t.channel === 'email' && t.subject ? t.subject : '—'}
                        </td>
                        <td className="px-6 py-4 text-gray-500 text-sm">
                          {new Date(t.updated_at).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Button variant="outline" size="sm" onClick={() => { setEditingTemplate(t); setActiveTab('editor'); }}>Edit</Button>
                            <Button variant="outline" size="sm" onClick={() => handleDelete(t.id)}>Delete</Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  );
}