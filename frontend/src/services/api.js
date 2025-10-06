const API_URL = import.meta.env.VITE_API_URL || 'YOUR_LAMBDA_FUNCTION_URL';
const API_KEY = import.meta.env.VITE_API_KEY;

const getHeaders = () => {
  const headers = {
    'x-api-key': API_KEY,
  };
  return headers;
};

export const generateVideo = async ({ prompt, image }) => {
  // Convert image file to base64
  const imageBase64 = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.readAsDataURL(image);
  });

  const response = await fetch(`${API_URL}/generate`, {
    method: 'POST',
    headers: {
      ...getHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt,
      image: imageBase64,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || error.message || 'Failed to generate video');
  }

  return response.json();
};

export const getVideos = async () => {
  const response = await fetch(`${API_URL}/videos`, {
    headers: getHeaders(),
  });

  if (!response.ok) {
    throw new Error('Failed to fetch videos');
  }

  return response.json();
};

export const getVideoStatus = async (videoId) => {
  const response = await fetch(`${API_URL}/videos/${videoId}`, {
    headers: getHeaders(),
  });

  if (!response.ok) {
    throw new Error('Failed to fetch video status');
  }

  return response.json();
};

export const refreshVideoUrl = async (videoId) => {
  const response = await fetch(`${API_URL}/videos/${videoId}/refresh-url`, {
    method: 'POST',
    headers: getHeaders(),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || 'Failed to refresh video URL');
  }

  return response.json();
};

export const deleteVideo = async (videoId) => {
  const response = await fetch(`${API_URL}/videos/${videoId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || 'Failed to delete video');
  }

  return response.json();
};
