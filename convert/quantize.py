import numpy as np


def quantise(img_array, n_colors, max_iter=100):
    """K-means colour quantisation. Returns (label_map, color_table)."""
    from sklearn.cluster import MiniBatchKMeans
    h, w, c = img_array.shape
    pixels = img_array.reshape(-1, c).astype(np.float32)
    km = MiniBatchKMeans(n_clusters=n_colors, random_state=42, max_iter=max_iter, n_init=3)
    labels = km.fit_predict(pixels)
    centers = np.clip(km.cluster_centers_, 0, 255).astype(np.uint8)
    return labels.reshape(h, w), centers
