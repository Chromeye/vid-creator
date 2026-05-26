import { useState, useRef } from 'react';
import { ChromePicker } from 'react-color';
import { useOnClickOutside } from '../utils/useOnClickOutside';
import { replaceVideoBackground } from '../services/api';

const getExpectedDims = (resolution) => {
    const r = (resolution || '').toLowerCase();
    if (r.includes('9:16')) return { width: 1080, height: 1920 };
    if (r.includes('1:1')) return { width: 1080, height: 1080 };
    if (r.includes('720p')) return { width: 1280, height: 720 };
    // '16:9, 1080p' and legacy '1080p' both fall through here
    return { width: 1920, height: 1080 };
};

export const VideoReplaceBackground = ({ id, resolution, onClose }) => {
    const expected = getExpectedDims(resolution);
    const [selectedFile, setSelectedFile] = useState(null);
    const [selectedColor, setSelectedColor] = useState(null);
    const [error, setError] = useState('');
    const [previewUrl, setPreviewUrl] = useState(null);
    const [loading, setLoading] = useState(false);
    const contentBoxRef = useRef(null);

    useOnClickOutside(contentBoxRef, onClose);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        setError('');

        if (!file) return;

        if (file.type !== 'image/jpeg' && file.type !== 'image/jpg') {
            setError('Please upload a valid JPG image.');
            return;
        }

        const img = new Image();
        const objectUrl = URL.createObjectURL(file);

        img.onload = () => {
            if (img.width !== expected.width || img.height !== expected.height) {
                setError(`Image dimensions must be exactly ${expected.width}x${expected.height} pixels to match the video.`);
                URL.revokeObjectURL(objectUrl);
                setSelectedFile(null);
                setPreviewUrl(null);
            } else {
                setSelectedFile(file);
                setPreviewUrl(objectUrl);
            }
        };

        img.onerror = () => {
            setError('Invalid image file.');
            URL.revokeObjectURL(objectUrl);
        };

        img.src = objectUrl;
    };

    const handleColorChange = (color) => {
        setSelectedColor(color.hex);
    };

    const handleSubmit = async () => {
        try {
            setLoading(true);
            setError('');

            const result = await replaceVideoBackground(id, {
                bgColor: selectedColor,
                bgImage: selectedFile
            });

            console.log('Background replacement started:', result);

            // Show success message with new video ID
            alert(`Background replacement started!\n\nNew video ID: ${result.videoId}\n\nThe video will appear in your list when processing is complete. This may take a few minutes.`);
            onClose();
        } catch (err) {
            console.error('Error replacing background:', err);
            setError(err.message || 'Failed to replace background');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className='video-viewer-overlay'>
            <div className='video-viewer-content' ref={contentBoxRef}>
                <h2>Replace Background</h2>

                <div className='form-body'>
                    <div className='upload-image'>
                        <div className='fields'>
                            <div className="form-group">
                                <label>Upload Image ({expected.width}x{expected.height} JPG)</label>
                                <input
                                    type='file'
                                    accept='.jpg, .jpeg'
                                    onChange={handleFileChange}
                                />
                            </div>
                            <div className='or'>OR</div>
                            <div className='form-group centred'>
                                <label style={{ marginBottom: '1rem' }}>Select Background Color</label>
                                <ChromePicker
                                    color={selectedColor || '#ffffff'}
                                    onChange={handleColorChange}
                                    disableAlpha={true}
                                />
                            </div>
                        </div>


                        {previewUrl && (
                            <div className="preview">
                                <div className='image-previews'>
                                    <div className='image-preview'>
                                        <img src={previewUrl} alt="Preview" />
                                        <p>{selectedFile.name}</p>
                                    </div>
                                </div>
                            </div>
                        )}

                    </div>

                    {error && <div className='error-message'>{error}</div>}





                    <div className='video-actions'>
                        <button
                            onClick={onClose}>
                            Cancel
                        </button>
                        <button

                            disabled={(!selectedFile && !selectedColor) || !!error || loading}
                            onClick={handleSubmit}
                        >
                            {loading ? 'Processing...' : 'Submit'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};