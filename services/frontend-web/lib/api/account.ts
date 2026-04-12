import apiClient from '../api-client';

export const accountAPI = {
  /**
   * Download all personal data as a ZIP archive.
   * Triggers a browser download automatically.
   */
  exportData: async (): Promise<void> => {
    const response = await apiClient.get('/api/v1/account/export', {
      responseType: 'blob',
    });

    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;

    // Try to read filename from Content-Disposition header
    const disposition = response.headers['content-disposition'] as string | undefined;
    let filename = 'rereflect-export.zip';
    if (disposition) {
      const match = disposition.match(/filename="?([^"]+)"?/);
      if (match) filename = match[1];
    }

    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },

  /**
   * Request account deletion.
   * The account will be deactivated immediately and permanently deleted
   * after 30 days unless cancelled.
   */
  requestDeletion: async (): Promise<{ message: string }> => {
    const response = await apiClient.post('/api/v1/account/delete-request');
    return response.data;
  },

  /**
   * Cancel a pending deletion request.
   * Reactivates the account and clears the deletion timestamp.
   */
  cancelDeletion: async (): Promise<{ message: string }> => {
    const response = await apiClient.post('/api/v1/account/cancel-deletion');
    return response.data;
  },
};
