import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNotify } from '../context/NotificationContext';
import { useLoading } from '../context/LoadingContext';
import { api } from '../api';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';

export default function AddProject() {
  const navigate = useNavigate();
  const notify = useNotify();
  const loadingCtrl = useLoading();

  const [formData, setFormData] = useState({
    name: '',
    description: '',
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      notify({ type: 'error', message: 'Project name is required' });
      return;
    }
    try {
      loadingCtrl.start();
      const res = await api.post('/projects', formData);
      notify({ type: 'success', message: 'Project created' });
      navigate(`/projects/${res.id}`);
    } catch (e) {
      notify({ type: 'error', message: e.message });
    } finally {
      loadingCtrl.stop();
    }
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-8">
      <div className="max-w-2xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold">New Project</h1>
          <p className="text-gray-500 mt-1">Create a new outreach project</p>
        </div>

        <Card className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Project Name</label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Q4 Outreach Campaign"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description (optional)</label>
              <textarea
                rows={4}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Describe this project..."
              />
            </div>

            <div className="flex gap-3 pt-4 border-t border-gray-200">
              <Button type="submit" disabled={loadingCtrl.loading}>
                {loadingCtrl.loading ? 'Creating…' : 'Create Project'}
              </Button>
              <Button variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}