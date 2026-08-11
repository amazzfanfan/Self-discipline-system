import { useEffect, useState } from 'react';
import api from '../services/api';

interface Props extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  src: string | null | undefined;
}

export default function PrivateImage({ src, alt = '', ...props }: Props) {
  const [imageState, setImageState] = useState<{ source: string; url: string } | null>(null);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    if (!src) return;
    const apiPath = src.startsWith('/api/') ? src.slice(4) : src;
    void api.get(apiPath, { responseType: 'blob' }).then((response) => {
      if (!active) return;
      createdUrl = URL.createObjectURL(response.data);
      setImageState({ source: src, url: createdUrl });
    }).catch(() => {
      if (active) setImageState(null);
    });
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [src]);

  if (!src || imageState?.source !== src) return null;
  return <img src={imageState.url} alt={alt} {...props} />;
}
