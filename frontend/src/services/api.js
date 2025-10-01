const API_URL = import.meta.env.VITE_API_URL || 'YOUR_LAMBDA_FUNCTION_URL';

export const generateVideo = async ({ prompt, image }) => {
  const formData = new FormData();
  formData.append('prompt', prompt);
  formData.append('image', image);

  const response = await fetch(`${API_URL}/generate`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || error.message || 'Failed to generate video');
  }

  return response.json();
};

export const getVideos = async () => {
  const response = await fetch(`${API_URL}/videos`);

  if (!response.ok) {
    throw new Error('Failed to fetch videos');
  }

  return response.json();
};

export const getVideoStatus = async (videoId) => {
  const response = await fetch(`${API_URL}/videos/${videoId}`);

  if (!response.ok) {
    throw new Error('Failed to fetch video status');
  }

  return response.json();
};
