import { useState, useEffect } from 'react';
import { getVideos, refreshVideoUrl } from '../services/api';

export default function VideoList({ refreshTrigger }) {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshingUrls, setRefreshingUrls] = useState(new Set());

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

  const handleRefreshUrl = async (videoId) => {
    setRefreshingUrls(prev => new Set(prev).add(videoId));

    try {
      const result = await refreshVideoUrl(videoId);

      // Update the video in the list with new URL
      setVideos(prevVideos =>
        prevVideos.map(video =>
          video.id === videoId
            ? { ...video, videoUrl: result.videoUrl }
            : video
        )
      );
    } catch (err) {
      console.error('Error refreshing URL:', err);
      alert(err.message || 'Failed to refresh URL');
    } finally {
      setRefreshingUrls(prev => {
        const newSet = new Set(prev);
        newSet.delete(videoId);
        return newSet;
      });
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

              {video.status === 'completed' && (
                <div className="video-actions">
                  {video.videoUrl ? (
                    <>
                      <a
                        href={video.videoUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="view-btn"
                      >
                        View Video
                      </a>
                      <a
                        href={video.videoUrl}
                        download
                        className="download-btn"
                      >
                        Download
                      </a>
                    </>
                  ) : null}
                  <button
                    onClick={() => handleRefreshUrl(video.id)}
                    disabled={refreshingUrls.has(video.id)}
                    className="refresh-url-btn"
                  >
                    {refreshingUrls.has(video.id) ? 'Refreshing...' : 'Refresh URL'}
                  </button>
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
