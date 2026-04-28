/**
 * CookieCutterPrintService - Frontend Logic
 * v4: soporte para dos piezas (cutter + stamp)
 */

let currentJob = null;
let scene, camera, renderer, controls, stlMesh;

const uploadZone    = document.getElementById('upload-zone');
const fileInput     = document.getElementById('file-input');
const previewImage  = document.getElementById('preview-image');
const btnGenerate   = document.getElementById('btn-generate');
const paramsToggle  = document.getElementById('params-toggle');
const paramsGrid    = document.getElementById('params-grid');
const stepResult    = document.getElementById('step-result');
const stepSuccess   = document.getElementById('step-success');
const orderForm     = document.getElementById('order-form');

// ============================================================
// Upload - Drag & Drop
// ============================================================
uploadZone.addEventListener('click', () => fileInput.click());

uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length) handleFile(files[0]);
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file) {
    const allowed = ['image/jpeg', 'image/jpg', 'image/png'];
    if (!allowed.includes(file.type)) {
        showToast('Formato no permitido. Usa JPG o PNG.', 'error');
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        showToast('Archivo demasiado grande. Max: 10 MB', 'error');
        return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        previewImage.classList.remove('hidden');
        uploadZone.querySelector('.upload-content').classList.add('hidden');
    };
    reader.readAsDataURL(file);
    uploadZone.dataset.file = 'ready';
    btnGenerate.disabled = false;
    showToast('Imagen cargada. Haz clic en "Generar cortante".', 'info');
}

paramsToggle.addEventListener('click', () => {
    paramsGrid.classList.toggle('hidden');
    paramsToggle.classList.toggle('active');
});

// ============================================================
// Generar STL y presupuesto
// ============================================================
btnGenerate.addEventListener('click', async () => {
    if (!fileInput.files.length) {
        showToast('Selecciona una imagen primero.', 'error');
        return;
    }
    setLoading(btnGenerate, true);
    try {
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        const wh = document.getElementById('wall-height').value;
        const wt = document.getElementById('wall-thickness').value;
        if (wh) formData.append('wall_height', wh);
        if (wt) formData.append('wall_thickness', wt);

        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (!res.ok || !data.exito) {
            throw new Error(data.detail || data.mensaje || 'Error desconocido');
        }

        currentJob = data;
        displayResults(data);

        stepResult.classList.remove('hidden');
        stepResult.scrollIntoView({ behavior: 'smooth', block: 'start' });

        // Preview 3D: cargamos el cutter
        initThreeJS();
        loadSTL(data.stl_cutter_url);

        showToast('¡Presupuesto generado! Dos piezas listas para descargar.', 'success');

    } catch (err) {
        console.error(err);
        showToast('Error: ' + err.message, 'error');
    } finally {
        setLoading(btnGenerate, false);
    }
});

function displayResults(data) {
    // Volumen y dimensiones
    const vol = data.volumen_cm3 || 0;
    document.getElementById('spec-volume').textContent = vol.toFixed(4) + ' cm³';

    const d = data.dimensiones_mm || data.dimensiones || [0, 0, 0];
    document.getElementById('spec-dims').textContent =
        `${d[0].toFixed(1)} x ${d[1].toFixed(1)} x ${d[2].toFixed(1)} mm`;

    // Precio
    const p = data.precio || {};
    const simb = p.simbolo || '$';
    document.getElementById('price-materials').textContent =
        `${simb}${(p.costo_materiales || 0).toFixed(2)}`;

    const base  = p.costo_base  || 0;
    const marg  = p.margen      || 1;
    const final = p.precio_final || 0;

    const elBase   = document.getElementById('price-base');
    const elMargin = document.getElementById('price-margin');
    if (elBase)   elBase.textContent   = `${simb}${base.toFixed(2)}`;
    if (elMargin) elMargin.textContent = `x${marg}`;

    document.getElementById('price-total').textContent =
        `${simb}${final.toFixed(2)} ${p.moneda || 'ARS'}`;

    // Botones de descarga — dos piezas
    const btnCutter = document.getElementById('download-cutter');
    const btnStamp  = document.getElementById('download-stamp');

    if (btnCutter) {
        btnCutter.href = data.stl_cutter_url || data.stl_url || '#';
    }
    if (btnStamp) {
        btnStamp.href = data.stl_stamp_url || '#';
    }

    // Compatibilidad con HTML viejo que solo tiene #download-stl
    const btnOld = document.getElementById('download-stl');
    if (btnOld) {
        btnOld.href = data.stl_cutter_url || data.stl_url || '#';
    }
}

// ============================================================
// Three.js - Visor 3D STL
// ============================================================
function initThreeJS() {
    const container = document.getElementById('threejs-container');
    if (!container) return;

    const width  = container.clientWidth  || 400;
    const height = container.clientHeight || 300;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f0f0);

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(10, 20, 10);
    scene.add(dirLight);

    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 0, 100);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate    = true;

    animate();
}

function animate() {
    requestAnimationFrame(animate);
    if (controls)  controls.update();
    if (renderer && scene && camera) renderer.render(scene, camera);
}

/**
 * Carga un STL desde una URL completa (no solo job_id).
 * CORREGIDO: recibe la URL directamente en lugar de construirla.
 */
function loadSTL(stlUrl) {
    if (!scene || !stlUrl || stlUrl === '#') return;
    const loader = new THREE.STLLoader();
    loader.load(
        stlUrl,
        (geometry) => displayGeometry(geometry),
        undefined,
        (err) => {
            console.error('Error cargando STL:', err);
            showToast('No se pudo cargar el preview 3D', 'warning');
        }
    );
}

function displayGeometry(geometry) {
    const material = new THREE.MeshPhongMaterial({
        color: 0xFF6B35,
        specular: 0x222222,
        shininess: 80,
    });

    if (stlMesh) {
        scene.remove(stlMesh);
        stlMesh.geometry.dispose();
    }

    stlMesh = new THREE.Mesh(geometry, material);
    geometry.computeBoundingBox();

    const center = new THREE.Vector3();
    geometry.boundingBox.getCenter(center);
    stlMesh.position.sub(center);

    const size = new THREE.Vector3();
    geometry.boundingBox.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    const scale  = 60 / maxDim;
    stlMesh.scale.set(scale, scale, scale);

    scene.add(stlMesh);
    if (controls) controls.reset();
}

// ============================================================
// Formulario de pedido
// ============================================================
orderForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentJob) return;

    const btn = orderForm.querySelector('button[type="submit"]');
    setLoading(btn, true);

    try {
        const formData = new FormData();
        formData.append('job_id',    currentJob.job_id);
        formData.append('nombre',    document.getElementById('order-name').value);
        formData.append('email',     document.getElementById('order-email').value);
        formData.append('telefono',  document.getElementById('order-phone').value || '');
        formData.append('aceptar',   'true');

        const res  = await fetch('/api/order', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error en pedido');

        stepResult.classList.add('hidden');
        document.getElementById('step-upload').classList.add('hidden');
        stepSuccess.classList.remove('hidden');

        document.getElementById('success-details').innerHTML = `
            <p><strong>Pedido:</strong> #${data.order_id}</p>
            <p><strong>Total:</strong> ${data.simbolo}${data.precio_final.toFixed(2)}</p>
        `;
    } catch (err) {
        showToast('Error: ' + err.message, 'error');
    } finally {
        setLoading(btn, false);
    }
});

// ============================================================
// Helpers
// ============================================================
function setLoading(btn, loading) {
    const text   = btn.querySelector('.btn-text');
    const loader = btn.querySelector('.btn-loader');
    if (loading) {
        btn.disabled = true;
        if (text)   text.classList.add('hidden');
        if (loader) loader.classList.remove('hidden');
    } else {
        btn.disabled = false;
        if (text)   text.classList.remove('hidden');
        if (loader) loader.classList.add('hidden');
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) { alert(message); return; }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => { if (toast.parentNode) toast.remove(); }, 4000);
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('Gema Makers - Cookie Cutter Service Ready v4');
});
