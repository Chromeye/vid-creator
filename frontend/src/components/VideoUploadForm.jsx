import { useState, useRef } from 'react';
import { useMyContext } from '../context/context-provider';

const VALID_DIMS = {
  '1280x720': '720p',
  '1920x1080': '1080p',
};

export default function VideoUploadForm({ onSubmit }) {
  const context = useMyContext();
  const [image, setImage] = useState({});
  const [preview, setPreview] = useState({});
  const [showFinalFrame, setShowFinalFrame] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState({});
  const [resolution, setResolution] = useState(null);

  const formRef = useRef(null);

  const handleImageChange = (e, position) => {
    const file = e.target.files[0];
    if (!file) return;
    const pos = position || 'start';

    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      setError((current) => ({ ...current, [pos]: 'Please upload a JPG or PNG file' }));
      return;
    }

    const img = new Image();
    img.onload = () => {
      const detected = VALID_DIMS[`${img.width}x${img.height}`];

      if (!detected) {
        setError((current) => ({
          ...current,
          [pos]: 'Image must be 1280×720 (720p) or 1920×1080 (1080p) at 16:9',
        }));
        setImage((current) => ({ ...current, [pos]: null }));
        setPreview((current) => ({ ...current, [pos]: null }));
        return;
      }

      if (pos === 'end' && resolution && detected !== resolution) {
        setError((current) => ({
          ...current,
          end: `Final frame must match start frame resolution (${resolution})`,
        }));
        setImage((current) => ({ ...current, end: null }));
        setPreview((current) => ({ ...current, end: null }));
        return;
      }

      if (pos === 'start') {
        setResolution(detected);
        setImage((current) => ({ ...current, end: null }));
        setPreview((current) => ({ ...current, end: null }));
        setError((current) => ({ ...current, end: '' }));
      }

      setError((current) => ({ ...current, [pos]: '' }));
      setImage((current) => ({ ...current, [pos]: file }));
      setPreview((current) => ({ ...current, [pos]: URL.createObjectURL(file) }));
    };
    img.src = URL.createObjectURL(file);
  };

  const isEmptyObject = (obj) =>
    (Object.keys(obj).length === 0 || Object.keys(obj).every((key) => obj[key] == null)) &&
    obj.constructor === Object;

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!context.data.prompt || !image.start) {
      setError((current) => ({ ...current, general: 'Please provide both a prompt and an image' }));
      return;
    }

    setIsSubmitting(true);
    setError({});

    try {
      await onSubmit({ prompt: context.data.prompt, image, model: context.data.model, resolution });
      context.updateValue('prompt', '');
      setImage({});
      setPreview({});
      setResolution(null);
    } catch (err) {
      setError((current) => ({ ...current, general: err.message || 'Failed to submit request' }));
    } finally {
      setIsSubmitting(false);
      if (formRef.current) {
        formRef.current.reset();
      }
    }
  };

  return (
    <div className='upload-form'>
      <h2>Generate Video</h2>

      <form onSubmit={handleSubmit} ref={formRef} className='form-body'>
        <div className='form-group'>
          <label htmlFor='model'>Model:</label>
          <select
            id='model'
            value={context.data.model || 'gemini-veo-31-fast'}
            className='model-options'
            onChange={(e) => context.updateValue('model', e.target.value)}
            disabled={isSubmitting}
          >
            <option value='gemini-veo-31-fast'>Veo 3.1 Fast</option>
            <option value='gemini-veo-31'>Veo 3.1</option>
            <option value='kling-v3-image-to-video'>Kling 3.0 Standard</option>
          </select>
        </div>
        <div className='form-group'>
          <label htmlFor='prompt'>Prompt:</label>
          <textarea
            id='prompt'
            value={context.data.prompt || ''}
            onChange={(e) => context.updateValue('prompt', e.target.value)}
            placeholder='Describe the video you want to generate...'
            rows='4'
            disabled={isSubmitting}
            required
          />
        </div>

        <div className='form-group'>
          <label htmlFor='image'>
            Start frame reference (1280×720 or 1920×1080, 16:9, JPG/PNG)
            {resolution && <span className='resolution-badge'> — {resolution} detected</span>}
            :
          </label>
          <input
            id='image'
            type='file'
            accept='image/jpeg,image/png'
            onChange={handleImageChange}
            disabled={isSubmitting}
            required
          />
          {error.start && <p className='error-message'>{error.start}</p>}
        </div>

        <div className='form-group final-frame-option'>
          <input
            type='checkbox'
            id='finalFrame'
            disabled={isSubmitting}
            checked={showFinalFrame}
            onChange={(e) => {
              setShowFinalFrame(e.target.checked);
              if (!e.target.checked) {
                setImage((current) => ({ ...current, end: null }));
                setPreview((current) => ({ ...current, end: null }));
              }
            }}
          />
          <label htmlFor='finalFrame'>Use image reference for the final frame, too?</label>
        </div>

        {showFinalFrame && (
          <div className='form-group'>
            <label htmlFor='imageEnd'>
              Final frame reference (must match start: {resolution ?? '720p or 1080p'}, JPG/PNG):
            </label>
            <input
              id='imageEnd'
              type='file'
              accept='image/jpeg,image/png'
              onChange={(e) => handleImageChange(e, 'end')}
              disabled={isSubmitting || !image.start}
              required
            />
            {error.end && <p className='error-message'>{error.end}</p>}
          </div>
        )}

        {!isEmptyObject(preview) && (
          <div className='image-previews'>
            {preview.start && <img src={preview.start} alt='First Frame Preview' />}
            {preview.end && <img src={preview.end} alt='Final Frame Preview' />}
          </div>
        )}
        {error.general && <p className='error-message'>{error.general}</p>}
        <button
          type='submit'
          disabled={isSubmitting || !(image.start && context.data.prompt) || (showFinalFrame && !image.end)}
        >
          {isSubmitting ? 'Submitting...' : 'Generate Video'}
        </button>
      </form>
    </div>
  );
}
