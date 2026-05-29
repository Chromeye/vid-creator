import { useState, useRef } from 'react';
import { useMyContext } from '../context/context-provider';

const VALID_DIMS = {
  '1080x1920': ['9:16', '1080p'],
  '1920x1080': ['16:9', '1080p'],
  '1080x1080': ['1:1', '1080p'],
  '720x1280':  ['9:16', '720p'],
  '1280x720':  ['16:9', '720p'],
  '720x720':   ['1:1',  '720p'],
};

// Veo 3.1 (Gemini) only accepts 16:9 and 9:16. Kling supports 1:1 as well.
const isVeoModel = (model) => typeof model === 'string' && model.startsWith('gemini-veo');
const aspectAllowedForModel = (aspect, model) => !(isVeoModel(model) && aspect === '1:1');

export default function VideoUploadForm({ onSubmit }) {
  const context = useMyContext();
  const [image, setImage] = useState({});
  const [preview, setPreview] = useState({});
  const [showFinalFrame, setShowFinalFrame] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState({});
  const [resolution, setResolution] = useState(null);

  const formRef = useRef(null);

  const validateAndSetImage = (file, position, modelOverride) => {
    if (!file) return;
    const pos = position || 'start';
    const activeModel = modelOverride ?? context.data.model;

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
          [pos]: 'Required: 1080p (1920×1080, 1080×1920, 1080×1080) or 720p (1280×720, 720×1280, 720×720)',
        }));
        setImage((current) => ({ ...current, [pos]: null }));
        setPreview((current) => ({ ...current, [pos]: null }));
        return;
      }

      if (!aspectAllowedForModel(detected[0], activeModel)) {
        setError((current) => ({
          ...current,
          [pos]: 'Veo 3.1 does not support 1:1. Use a 16:9 or 9:16 image, or switch to Kling.',
        }));
        setImage((current) => ({ ...current, [pos]: null }));
        setPreview((current) => ({ ...current, [pos]: null }));
        return;
      }

      if (pos === 'end' && resolution && detected[0] !== resolution[0]) {
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

  const handleImageChange = (e, position) => {
    validateAndSetImage(e.target.files[0], position);
  };

  const revalidateInputsForModel = (nextModel) => {
    // Clear previous upload errors and re-run validation against whatever
    // files are still present in the file inputs.
    setError((current) => ({ ...current, start: '', end: '' }));
    setImage({});
    setPreview({});
    setResolution(null);
    const form = formRef.current;
    if (!form) return;
    const startFile = form.querySelector('#image')?.files?.[0];
    const endFile = form.querySelector('#imageEnd')?.files?.[0];
    if (startFile) validateAndSetImage(startFile, 'start', nextModel);
    if (endFile) validateAndSetImage(endFile, 'end', nextModel);
  };

  const isEmptyObject = (obj) => (Object.keys(obj).length === 0 || Object.keys(obj).every((key) => obj[key] == null)) && obj.constructor === Object;

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
            onChange={(e) => {
              const nextModel = e.target.value;
              context.updateValue('model', nextModel);
              revalidateInputsForModel(nextModel);
            }}
            disabled={isSubmitting}
          >
            <option value='gemini-veo-31-fast'>Veo 3.1 Fast</option>
            <option value='gemini-veo-31'>Veo 3.1</option>
            <option value='kling-v3-image-to-video'>Kling 3.0 Standard</option>
            <option value='seedance-2-image-to-video'>Seedance 2.0</option>
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
            Start frame reference (1080p or 720p in 16:9, 9:16
            {isVeoModel(context.data.model) ? '' : ', 1:1'}, JPG/PNG)
            {resolution && <span className='resolution-badge'> — {resolution.join(', ')} detected</span>}:
          </label>
          <input id='image' type='file' accept='image/jpeg,image/png' onChange={handleImageChange} disabled={isSubmitting} required />
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
            <label htmlFor='imageEnd'>Final frame reference (must match start: {resolution ? resolution.join(', ') : (isVeoModel(context.data.model) ? '1080p or 720p (9:16, 16:9)' : '1080p or 720p (9:16, 16:9, 1:1)')}, JPG/PNG):</label>
            <input id='imageEnd' type='file' accept='image/jpeg,image/png' onChange={(e) => handleImageChange(e, 'end')} disabled={isSubmitting || !image.start} required />
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
        <button type='submit' disabled={isSubmitting || !(image.start && context.data.prompt) || (showFinalFrame && !image.end)}>
          {isSubmitting ? 'Submitting...' : 'Generate Video'}
        </button>
      </form>
    </div>
  );
}
