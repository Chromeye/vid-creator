import { useState, useEffect } from 'react';
import { getVideos } from '../services/api';

export default function VideoList({ refreshTrigger }) {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchVideos();
  }, [refreshTrigger]);

  const fetchVideos = async () => {
    setLoading(true);
    setError('');

    try {
      const data = await getVideos();
      setVideos(data.videos || []);
    } catch (err) {
      setError(err.message || 'Failed to load videos');
      console.error('Error fetching videos:', err);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed':
        return '#56bd52';
      case 'processing':
        return '#ff9800';
      case 'failed':
        return '#ea4335';
      default:
        return '#757575';
    }
  };

  if (loading) {
    return <div className="video-list loading">Loading videos...</div>;
  }

  if (error) {
    return (
      <div className="video-list error">
        <p>{error}</p>
        <button onClick={fetchVideos}>Retry</button>
      </div>
    );
  }

  return (
    <div className="video-list">
      <div className="list-header">
        <h2>Generated Videos</h2>
        <button onClick={fetchVideos} className="refresh-btn">Refresh</button>
      </div>

      {videos.length === 0 ? (
        <p className="no-videos">No videos generated yet</p>
      ) : (
        <div className="videos-grid">
          {videos.map((video) => (
            <div key={video.id} className="video-card">
              <div className="video-info">
                <h3>{video.prompt}</h3>
                <p className="video-date">
                  {new Date(video.createdAt).toLocaleString()}
                </p>
                <div className="video-status">
                  <span
                    className="status-indicator"
                    style={{ backgroundColor: getStatusColor(video.status) }}
                  />
                  <span>{video.status}</span>
                </div>
              </div>

              {video.status === 'completed' && video.s3Url && (
                <div className="video-actions">
                  <a
                    href={video.s3Url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="view-btn"
                  >
                    View Video
                  </a>
                  <a
                    href={video.s3Url}
                    download
                    className="download-btn"
                  >
                    Download
                  </a>
                </div>
              )}

              {video.status === 'processing' && (
                <div className="processing-indicator">
                  <div className="spinner"></div>
                  <span>Processing...</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
