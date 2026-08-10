import { useEffect, useState } from 'react';
import api from '../services/api';

interface Props extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  src: string | null | undefined;
}

export default function PrivateImage({ src, alt = '', ...props }: Props) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    if (!src) return;
    const apiPath = src.startsWith('/api/') ? src.slice(4) : src;
    void api.get(apiPath, { responseType: 'blob' }).then((response) => {
      if (!active) return;
      createdUrl = URL.createObjectURL(response.data);
      setObjectUrl(createdUrl);
    }).catch(() => {
      if (active) setObjectUrl(null);
    });
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [src]);

  if (!objectUrl) return null;
  return <img src={objectUrl} alt={alt} {...props} />;
}
