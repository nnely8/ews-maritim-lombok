import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from branca.element import Template, MacroElement
from streamlit_autorefresh import st_autorefresh
import os
import plotly.graph_objects as go
import numpy as np 

# --- KONFIGURASI UTAMA ---
AWSCENTER_USERNAME = "97240"
AWSCENTER_PASSWORD = "97240@2020"

BATAS_SEDANG = 1.25
BATAS_TINGGI = 2.50
BATAS_SANGAT_TINGGI = 4.00
BATAS_EKSTREM = 6.00

HISTORY_FILE = "history_gelombang.csv"

PARAM_MAP = {
    'Water Level': {'url_part': 'waterlevel', 'val_col': 'wl', 'unit': 'm'},
    'Hujan': {'url_part': 'hujan', 'val_col': 'curah', 'unit': 'mm'},
    'Suhu': {'url_part': 'suhu', 'val_col': 'curah', 'unit': '°C'},
    'Kelembaban': {'url_part': 'kelembaban', 'val_col': 'curah', 'unit': '%'},
    'Kecepatan Angin': {'url_part': 'kecepatanangin', 'val_col': 'kecepatanangin', 'unit': 'm/s'},
    'Arah Angin': {'url_part': 'arahangin', 'val_col': 'arahangin', 'unit': '°'},
    'Radiasi Matahari': {'url_part': 'matahari', 'val_col': 'radiasi', 'unit': 'W/m²'},
    'Tekanan Udara': {'url_part': 'tekananudara', 'val_col': 'pp_air', 'unit': 'mbar'}
}

st.set_page_config(page_title="Peta EWS AWS Maritim", page_icon="🌊", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; }
        h1 { margin-top: -2rem !important; padding-top: 0rem !important; }
        header { background-color: transparent !important; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=300000, limit=None, key="maritim_refresh")

@st.cache_data(ttl=300) 
def fetch_all_data():
    session = requests.Session()
    login_url = "https://awscenter.bmkg.go.id/base/verify"
    login_data = {"username": AWSCENTER_USERNAME, "password": AWSCENTER_PASSWORD}
    
    if session.post(login_url, data=login_data).status_code != 200:
        return None, "Gagal login ke AWSCenter."

    try:
        res_map = session.get("https://awscenter.bmkg.go.id/base/marker_login_map").json()
        df_stations = pd.DataFrame(res_map)
        target_sites = 'Lembar|Pemenang|Kayangan'
        df_stations = df_stations[df_stations['name_station'].str.contains(target_sites, case=False, na=False)]
        df_stations = df_stations[~df_stations['name_station'].str.contains('ARG Pemenang', case=False, na=False)]
        
        df_stations['lat'] = pd.to_numeric(df_stations['lat'], errors='coerce')
        df_stations['lng'] = pd.to_numeric(df_stations['lng'], errors='coerce')
        df_stations = df_stations.dropna(subset=['lat', 'lng'])
        
        df_main = df_stations[['id_station', 'name_station', 'nama_kota', 'lat', 'lng']].copy()
        df_main['tanggal'] = df_stations.get('tanggal', 'N/A') 
    except Exception as e:
        return None, f"Gagal mengambil koordinat stasiun: {e}"

    for param_name, config in PARAM_MAP.items():
        api_url = f"https://awscenter.bmkg.go.id/dashboard/get_parameter_terkini_{config['url_part']}"
        try:
            res_param = session.get(api_url).json()
            df_param = pd.DataFrame(res_param)
            if not df_param.empty and config['val_col'] in df_param.columns:
                df_param[param_name] = pd.to_numeric(df_param[config['val_col']], errors='coerce')
                df_param = df_param[['id_station', param_name]]
                df_main = pd.merge(df_main, df_param, on='id_station', how='left')
            else:
                df_main[param_name] = None
        except Exception:
            df_main[param_name] = None 
            
    for param_name in PARAM_MAP.keys():
        if param_name in df_main.columns:
            df_main[param_name] = df_main[param_name].fillna(0)
        else:
            df_main[param_name] = 0

    current_history = df_main[['tanggal', 'name_station', 'Water Level']].copy()
    current_history = current_history[current_history['tanggal'] != 'N/A'] 
    
    if os.path.exists(HISTORY_FILE):
        df_history = pd.read_csv(HISTORY_FILE)
        df_history = pd.concat([df_history, current_history])
        df_history = df_history.drop_duplicates(subset=['tanggal', 'name_station'])
    else:
        df_history = current_history
        
    df_history.to_csv(HISTORY_FILE, index=False)
    return df_main, None

# --- TAMPILAN DASHBOARD ---
st.title("🌊 Peta Peringatan Dini Tinggi Gelombang Jalur Penyeberangan NTB")
st.markdown("Monitoring Site: **Pelabuhan Lembar, Pemenang, Kayangan**")

with st.spinner('Memuat peta dan menarik data dari AWSCenter...'):
    df, error = fetch_all_data()

if error:
    st.error(error)
elif df.empty:
    st.warning("⚠️ Data stasiun untuk Lembar, Pemenang, atau Kayangan tidak ditemukan di API saat ini.")
else:
    df_ekstrem = df[df['Water Level'] > BATAS_EKSTREM]
    df_sangat_tinggi = df[(df['Water Level'] >= BATAS_SANGAT_TINGGI) & (df['Water Level'] <= BATAS_EKSTREM)]
    df_tinggi = df[(df['Water Level'] >= BATAS_TINGGI) & (df['Water Level'] < BATAS_SANGAT_TINGGI)]
    df_sedang = df[(df['Water Level'] >= BATAS_SEDANG) & (df['Water Level'] < BATAS_TINGGI)]

    if not df_ekstrem.empty:
        st.error(f"☠️ PERINGATAN EKSTREM: {len(df_ekstrem)} stasiun mendeteksi gelombang > {BATAS_EKSTREM} meter!")
    elif not df_sangat_tinggi.empty:
        st.error(f"🚨 PERINGATAN SANGAT TINGGI: {len(df_sangat_tinggi)} stasiun mendeteksi gelombang 4.0 - 6.0 meter!")
    elif not df_tinggi.empty:
        st.error(f"⚠️ PERINGATAN TINGGI (BAHAYA): {len(df_tinggi)} stasiun mendeteksi gelombang 2.5 - 4.0 meter!")
    elif not df_sedang.empty:
        st.warning(f"🟡 PERINGATAN SEDANG (WASPADA): {len(df_sedang)} stasiun mendeteksi gelombang 1.25 - 2.5 meter.")
    else:
        st.success("✅ Kondisi tinggi gelombang di semua site terpantau AMAN / RENDAH (< 1.25 meter).")

    center_lat = df['lat'].mean()
    center_lon = df['lng'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles='OpenStreetMap')

    for idx, row in df.iterrows():
        popup_html = f"<div style='min-width: 220px; font-size: 14px;'>"
        popup_html += f"<b>{row['name_station']}</b><br>"
        popup_html += f"<span style='color: gray; font-size: 12px;'>{row['nama_kota']}</span><br>"
        popup_html += f"<span style='color: #007bff; font-size: 11px;'>🕒 Update: {row['tanggal']} UTC</span><hr style='margin: 8px 0;'>"
        for p_name, p_config in PARAM_MAP.items():
            val = row[p_name]
            popup_html += f"<b>{p_name}:</b> {val} {p_config['unit']}<br>"
        popup_html += "</div>"

        wl_val = row['Water Level']
        if wl_val > BATAS_EKSTREM:
            pin_color = 'black'; pin_icon = 'flash' 
        elif wl_val >= BATAS_SANGAT_TINGGI:
            pin_color = 'darkred'; pin_icon = 'exclamation-sign' 
        elif wl_val >= BATAS_TINGGI:
            pin_color = 'red'; pin_icon = 'warning-sign' 
        elif wl_val >= BATAS_SEDANG:
            pin_color = 'orange'; pin_icon = 'info-sign' 
        else:
            pin_color = 'green'; pin_icon = 'tint' 

        folium.Marker(
            location=[row['lat'], row['lng']],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f"{row['name_station']}",
            icon=folium.Icon(color=pin_color, icon=pin_icon)
        ).add_to(m)

    template = """
    {% macro html(this, kwargs) %}
    <div style="position: absolute; bottom: 30px; left: 30px; width: 310px; height: 180px; background-color: white; border: 2px solid grey; z-index:9999; font-size:13px; color: black; padding: 10px; border-radius: 8px; box-shadow: 3px 3px 5px rgba(0,0,0,0.3);">
        <b style="color: black;">🌊 Kategori Gelombang (BMKG)</b><br>
        <hr style="margin: 5px 0; border: 1px solid grey;">
        <i class="fa fa-bolt" style="color:black; margin-right: 5px; width: 15px; text-align: center;"></i> <span style="color: black;">Ekstrem (&gt; 6.00 m)</span><br>
        <i class="fa fa-exclamation-triangle" style="color:darkred; margin-right: 5px; width: 15px; text-align: center;"></i> <span style="color: black;">Sangat Tinggi (4.00 - 6.00 m)</span><br>
        <i class="fa fa-exclamation-circle" style="color:red; margin-right: 5px; width: 15px; text-align: center;"></i> <span style="color: black;">Tinggi (2.50 - 3.99 m)</span><br>
        <i class="fa fa-info-circle" style="color:orange; margin-right: 5px; width: 15px; text-align: center;"></i> <span style="color: black;">Sedang (1.25 - 2.49 m)</span><br>
        <i class="fa fa-tint" style="color:green; margin-right: 5px; width: 15px; text-align: center;"></i> <span style="color: black;">Rendah (&lt; 1.25 m)</span>
    </div>
    {% endmacro %}
    """
    macro = MacroElement()
    macro._template = Template(template)
    m.get_root().add_child(macro)

    map_data = st_folium(m, use_container_width=True, height=650, returned_objects=["last_object_clicked"])

    # --- 📈 PANEL DETAIL & GRAFIK ---
    if map_data and map_data.get("last_object_clicked"):
        clicked_lat = map_data["last_object_clicked"]["lat"]
        clicked_lng = map_data["last_object_clicked"]["lng"]
        
        df['dist'] = (df['lat'] - clicked_lat)**2 + (df['lng'] - clicked_lng)**2
        closest_idx = df['dist'].idxmin()
        
        if df.loc[closest_idx, 'dist'] < 0.001:
            selected_station = df.loc[closest_idx, 'name_station']
            current_wl = df.loc[closest_idx, 'Water Level']
            current_time = df.loc[closest_idx, 'tanggal']
            
            st.markdown("---")
            st.subheader(f"📊 Dashboard Analisis: {selected_station}")
            
            if current_wl > BATAS_EKSTREM:
                bg_color, border_color, text_color = "#333333", "#000000", "#ffffff" 
                title = "Peringatan Gelombang Ekstrem"
                icon = "☠️"
                desc = f"Terdapat potensi gelombang EKSTREM dengan ketinggian {current_wl:.2f}m. SANGAT BERBAHAYA bagi SEMUA aktivitas di perairan. Harap hentikan seluruh kegiatan pelayaran!"
            elif current_wl >= BATAS_SANGAT_TINGGI:
                bg_color, border_color, text_color = "#ffebee", "#c62828", "#c62828" 
                title = "Peringatan Gelombang Sangat Tinggi"
                icon = "🚨"
                desc = f"Terdapat potensi gelombang sangat tinggi mencapai {current_wl:.2f}m. BERBAHAYA bagi SEMUA jenis kapal, termasuk kapal berukuran besar. Ikuti arahan otoritas setempat."
            elif current_wl >= BATAS_TINGGI:
                bg_color, border_color, text_color = "#fff0f0", "#e53935", "#d32f2f" 
                title = "Peringatan Gelombang Tinggi"
                icon = "⚠️"
                desc = f"Terdapat potensi gelombang tinggi mencapai {current_wl:.2f}m. SANGAT BERBAHAYA bagi perahu nelayan, tongkang, dan kapal feri. Harap berhati-hati dan ikuti arahan dari otoritas setempat."
            elif current_wl >= BATAS_SEDANG:
                bg_color, border_color, text_color = "#fff8e1", "#ffb300", "#f57f17" 
                title = "Peringatan Gelombang Sedang"
                icon = "🟡"
                desc = f"Terdapat potensi gelombang sedang dengan ketinggian {current_wl:.2f}m pada perairan ini. Berisiko bagi perahu nelayan dan kapal kecil. Harap berhati-hati dan ikuti arahan dari otoritas setempat."
            else:
                bg_color, border_color, text_color = "#e8f5e9", "#43a047", "#2e7d32" 
                title = "Kondisi Perairan Aman"
                icon = "✅"
                desc = f"Tinggi gelombang saat ini {current_wl:.2f}m. Kondisi perairan terpantau relatif aman untuk aktivitas nelayan dan penyeberangan normal."

            alert_html = f"""
            <div style="
                background-color: {bg_color};
                border-left: 5px solid {border_color};
                padding: 15px 20px;
                border-radius: 6px;
                margin-bottom: 20px;
                font-family: sans-serif;
            ">
                <div style="display: flex; align-items: center; color: {text_color}; font-weight: bold; font-size: 18px; margin-bottom: 8px;">
                    <span style="font-size: 22px; margin-right: 10px;">{icon}</span> {title}
                </div>
                <div style="color: {'#e0e0e0' if current_wl > BATAS_EKSTREM else '#555555'}; font-size: 15px; line-height: 1.5;">
                    {desc}
                </div>
            </div>
            """
            st.markdown(alert_html, unsafe_allow_html=True)

            if os.path.exists(HISTORY_FILE):
                df_hist = pd.read_csv(HISTORY_FILE)
                df_hist = df_hist[df_hist['name_station'] == selected_station]
                
                if not df_hist.empty:
                    df_hist['tanggal'] = pd.to_datetime(df_hist['tanggal'])
                    df_hist = df_hist.set_index('tanggal')
                    df_resampled = df_hist['Water Level'].resample('30min').mean().reset_index()
                    df_resampled = df_resampled.dropna()
                    
                    if not df_resampled.empty:
                        trend_msg = "Menganalisis..."
                        if len(df_resampled) >= 3:
                            y = df_resampled['Water Level'].values[-10:] 
                            x = np.arange(len(y))
                            slope, _ = np.polyfit(x, y, 1) 
                            
                            if slope > 0.02:
                                trend_msg = "NAIK ↗️ (Gelombang berpotensi makin tinggi)"
                            elif slope < -0.02:
                                trend_msg = "TURUN ↘️ (Gelombang berpotensi mereda)"
                            else:
                                trend_msg = "STABIL ➡️ (Kondisi cenderung tetap)"
                        else:
                            trend_msg = "STABIL ➡️ (Data historis belum cukup untuk prediksi AI)"

                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=df_resampled['tanggal'], y=df_resampled['Water Level'],
                                mode='lines+markers', line=dict(color='#ff4b4b', width=3, shape='spline'), 
                                marker=dict(size=6, color='#ff4b4b', symbol='circle'),
                                fill='tozeroy', fillcolor='rgba(255, 75, 75, 0.15)', name='Tinggi Gelombang',
                                hovertemplate='<b>Waktu:</b> %{x|%d %b %Y %H:%M} UTC<br><b>Tinggi:</b> %{y:.2f} m<extra></extra>'
                            ))
                            
                            fig.update_layout(
                                xaxis=dict(
                                    rangeselector=dict(
                                        buttons=list([
                                            dict(count=24, label="24 jam", step="hour", stepmode="backward"),
                                            dict(count=3, label="3 hari", step="day", stepmode="backward"),
                                            dict(count=7, label="7 hari", step="day", stepmode="backward"),
                                            dict(step="all", label="Semua")
                                        ]),
                                        bgcolor="rgba(255, 255, 255, 0.1)",
                                        activecolor="rgba(255, 255, 255, 0.3)"
                                    ),
                                    rangeslider=dict(visible=True, thickness=0.08), 
                                    type="date", 
                                    showgrid=True, 
                                    gridcolor='rgba(128, 128, 128, 0.2)'
                                ),
                                yaxis=dict(title="Tinggi Gelombang (Meter)", showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)'),
                                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=20, r=20, t=30, b=20), height=350
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        with col2:
                            st.info(f"**🤖 AI Trend Analysis:**\n\n{trend_msg}")
                            
                            wa_report = f"""🚨 *LAPORAN EWS MARITIM BMKG* 🚨
📍 *Lokasi:* {selected_station}
🕒 *Update:* {current_time} UTC

🌊 *Tinggi Gelombang:* {current_wl:.2f} m 
📊 *Status:* {title.replace('Peringatan ', '')}
🤖 *Prediksi Tren:* {trend_msg}

🚤 *Peringatan Keselamatan:*
{desc}

_Pesan otomatis dikirim dari Dashboard EWS Maritim NTB_"""

                            st.markdown("📲 **Bagikan Info Risiko:**")
                            st.download_button(
                                label="📥 Download Teks Laporan (WA)",
                                data=wa_report,
                                file_name=f"Laporan_{selected_station.replace(' ', '_')}.txt",
                                mime="text/plain"
                            )
                            st.caption("Download rangkuman teks untuk grup WA.")
                            
                            # 🎯 FITUR BARU: DOWNLOAD DATA CSV (PASANG SURUT)
                            st.markdown("---")
                            st.markdown("💾 **Data Historis Pasang Surut:**")
                            
                            # Siapkan dataframe yang rapi untuk di-download
                            df_download = df_resampled.copy()
                            df_download.rename(columns={'tanggal': 'Waktu (UTC)', 'Water Level': 'Tinggi Gelombang (m)'}, inplace=True)
                            csv_data = df_download.to_csv(index=False).encode('utf-8')
                            
                            st.download_button(
                                label="📊 Download Data CSV",
                                data=csv_data,
                                file_name=f"Data_Pasut_{selected_station.replace(' ', '_')}.csv",
                                mime="text/csv"
                            )
                            st.caption("Unduh data historis gelombang per 30 menit (format CSV) untuk analisis lanjutan pelabuhan/akademisi.")
                    else:
                        st.info("🕒 Sedang mengumpulkan data per 30 menit dari server...")
                else:
                    st.info(f"Belum ada rekaman riwayat untuk {selected_station}.")

    # --- TABEL DATA ---
    st.markdown("---")
    st.subheader("📋 Tabel Data Terkini Stasiun Maritim")
    df_tabel = df.drop(columns=['lat', 'lng', 'id_station', 'dist'], errors='ignore')
    df_tabel = df_tabel.rename(columns={'name_station': 'Nama Stasiun', 'nama_kota': 'Kab/Kota', 'tanggal': 'Update Terakhir (UTC)'})
    cols = ['Nama Stasiun', 'Kab/Kota', 'Update Terakhir (UTC)'] + list(PARAM_MAP.keys())
    df_tabel = df_tabel[cols]
    styled_tabel = df_tabel.style.format(precision=2)
    st.dataframe(styled_tabel, use_container_width=True, hide_index=True)
