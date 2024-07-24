import os
import csv
from dotenv import load_dotenv
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QDateEdit, QSpinBox, QFileDialog, QTextEdit, QCheckBox,
    QMessageBox, QScrollArea
)
from PyQt6.QtCore import QDate, Qt
from youtubesearchpython import VideosSearch
from youtube_transcript_api import YouTubeTranscriptApi
import webbrowser

# Load environment variables
load_dotenv()

# Get API key from environment variable
api_key = os.getenv("YOUTUBE_API_KEY")

# Initialize the YouTube API client
youtube = None
if api_key:
    youtube = build('youtube', 'v3', developerKey=api_key)


def search_videos_with_api(query, max_results=50):
    request = youtube.search().list(
        q=query,
        type='video',
        part='id,snippet',
        maxResults=max_results
    )
    response = request.execute()
    return response['items']


def search_videos_without_api(query, max_results=50):
    try:
        videos_search = VideosSearch(query, limit=max_results)
        results = videos_search.result()['result']
        if not results:
            raise ValueError("No results found")
        return results
    except Exception as e:
        print(f"Error in search_videos_without_api: {e}")
        return []


def get_video_details(video_ids):
    request = youtube.videos().list(
        part='snippet,statistics',
        id=','.join(video_ids)
    )
    response = request.execute()
    return response['items']


def parse_relative_time(time_str):
    if not time_str or 'Streamed' in time_str:
        return datetime.now()

    current_time = datetime.now()
    time_parts = time_str.split()

    if len(time_parts) < 2:
        return current_time

    try:
        value = int(time_parts[0])
        unit = time_parts[1].lower()

        if 'hour' in unit:
            return current_time - timedelta(hours=value)
        elif 'day' in unit:
            return current_time - timedelta(days=value)
        elif 'week' in unit:
            return current_time - timedelta(weeks=value)
        elif 'month' in unit:
            return current_time - timedelta(days=value * 30)
        elif 'year' in unit:
            return current_time - timedelta(days=value * 365)
        else:
            return current_time
    except ValueError:
        return current_time


def filter_videos_by_date_range(videos, start_date, end_date, use_api):
    filtered_videos = []
    for video in videos:
        if use_api:
            publish_date = datetime.strptime(video['snippet']['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
        else:
            publish_date = parse_relative_time(video.get('publishedTime', ''))
        if start_date <= publish_date <= end_date:
            filtered_videos.append(video)
    return filtered_videos


def export_to_csv(videos, filename, use_api):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Title', 'Channel', 'View Count', 'Publish Date', 'Video ID'])

        for video in videos:
            if use_api:
                writer.writerow([
                    video['snippet']['title'],
                    video['snippet']['channelTitle'],
                    video['statistics'].get('viewCount', 'N/A'),
                    video['snippet']['publishedAt'],
                    video['id']
                ])
            else:
                writer.writerow([
                    video.get('title', 'N/A'),
                    video.get('channel', {}).get('name', 'N/A'),
                    video.get('viewCount', {}).get('text', 'N/A'),
                    video.get('publishedTime', 'N/A'),
                    video.get('id', 'N/A')
                ])


class YouTubeAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.transcript_windows = []
        self.transcript_directory = os.path.join(os.getcwd(), 'transcripts')
        os.makedirs(self.transcript_directory, exist_ok=True)
        self.initUI()

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Search input
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel('Search:'))
        self.search_input = QLineEdit()
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Max results input
        max_results_layout = QHBoxLayout()
        max_results_layout.addWidget(QLabel('Max Results:'))
        self.max_results_input = QSpinBox()
        self.max_results_input.setRange(1, 50)
        self.max_results_input.setValue(50)
        max_results_layout.addWidget(self.max_results_input)
        layout.addLayout(max_results_layout)

        # Date range inputs
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel('Start Date:'))
        self.start_date = QDateEdit(QDate.currentDate().addDays(-7))
        date_layout.addWidget(self.start_date)
        date_layout.addWidget(QLabel('End Date:'))
        self.end_date = QDateEdit(QDate.currentDate())
        date_layout.addWidget(self.end_date)
        layout.addLayout(date_layout)

        # API key checkbox
        self.use_api_checkbox = QCheckBox('Use YouTube API')
        self.use_api_checkbox.setChecked(True)
        layout.addWidget(self.use_api_checkbox)

        # Search button
        self.search_button = QPushButton('Search Videos')
        self.search_button.clicked.connect(self.search_and_display_videos)
        layout.addWidget(self.search_button)

        # Results display
        self.results_area = QScrollArea()
        self.results_widget = QWidget()
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_area.setWidget(self.results_widget)
        self.results_area.setWidgetResizable(True)
        layout.addWidget(self.results_area)

        # Export button
        self.export_button = QPushButton('Export Results to CSV')
        self.export_button.clicked.connect(self.export_results)
        layout.addWidget(self.export_button)

        # Change transcript directory button
        change_dir_button = QPushButton("Change Transcript Directory")
        change_dir_button.clicked.connect(self.change_transcript_directory)
        layout.addWidget(change_dir_button)

        self.setWindowTitle('YouTube Analyzer')
        self.setGeometry(100, 100, 800, 600)

    def search_and_display_videos(self):
        query = self.search_input.text()
        max_results = self.max_results_input.value()
        start_date = datetime.combine(self.start_date.date().toPyDate(), datetime.min.time())
        end_date = datetime.combine(self.end_date.date().toPyDate(), datetime.max.time())
        self.use_api = self.use_api_checkbox.isChecked()

        try:
            if self.use_api and youtube:
                search_results = search_videos_with_api(query, max_results)
                video_ids = [item['id']['videoId'] for item in search_results]
                video_details = get_video_details(video_ids)
                filtered_videos = filter_videos_by_date_range(video_details, start_date, end_date, self.use_api)
            else:
                search_results = search_videos_without_api(query, max_results)
                if not search_results:
                    raise ValueError("No results found")
                filtered_videos = filter_videos_by_date_range(search_results, start_date, end_date, self.use_api)

            if not filtered_videos:
                QMessageBox.information(self, "No Results",
                                        "No results found. Please try a different query or date range.")
            else:
                self.video_results = filtered_videos
                self.display_results(filtered_videos)
        except Exception as e:
            print(f"An error occurred: {e}")
            QMessageBox.warning(self, "Error", f"An error occurred: {str(e)}")

    def display_results(self, videos):
        # Clear previous results
        for i in reversed(range(self.results_layout.count())):
            self.results_layout.itemAt(i).widget().setParent(None)

        for video in videos:
            if self.use_api:
                title = video['snippet']['title']
                channel = video['snippet']['channelTitle']
                views = video['statistics'].get('viewCount', 'N/A')
                published = video['snippet']['publishedAt']
                video_id = video['id']
            else:
                title = video.get('title', 'N/A')
                channel = video.get('channel', {}).get('name', 'N/A')
                views = video.get('viewCount', {}).get('text', 'N/A')
                published = video.get('publishedTime', 'N/A')
                video_id = video.get('id', 'N/A')

            result_text = f"Title: {title}\n"
            result_text += f"Channel: {channel}\n"
            result_text += f"Views: {views}\n"
            result_text += f"Published: {published}\n"
            result_text += f"Video ID: {video_id}\n"

            result_widget = QWidget()
            result_layout = QVBoxLayout(result_widget)

            result_label = QLabel(result_text)
            result_label.setWordWrap(True)
            result_layout.addWidget(result_label)

            button_layout = QHBoxLayout()
            view_button = QPushButton("View")
            transcribe_button = QPushButton("Transcribe")

            view_button.clicked.connect(lambda _, vid=video_id: self.view_video(vid))
            transcribe_button.clicked.connect(lambda _, vid=video_id: self.show_transcript(vid))

            button_layout.addWidget(view_button)
            button_layout.addWidget(transcribe_button)
            result_layout.addLayout(button_layout)

            self.results_layout.addWidget(result_widget)

    def view_video(self, video_id):
        webbrowser.open(f"https://www.youtube.com/watch?v={video_id}")

    def show_transcript(self, video_id):
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            transcript_text = "\n".join([f"{entry['start']:.2f} - {entry['text']}" for entry in transcript])

            # Save transcript to file
            file_path = os.path.join(self.transcript_directory, f'{video_id}_transcript.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(transcript_text)

            # Create and display transcript in a new window
            transcript_window = QWidget()
            transcript_window.setWindowTitle(f"Transcript for video {video_id}")
            transcript_layout = QVBoxLayout()
            transcript_display = QTextEdit()
            transcript_display.setPlainText(transcript_text)
            transcript_display.setReadOnly(True)
            transcript_layout.addWidget(transcript_display)

            # Add a label to show where the transcript is saved
            save_label = QLabel(f"Transcript saved to: {file_path}")
            transcript_layout.addWidget(save_label)

            # Add a button to open the transcript directory
            open_dir_button = QPushButton("Open Transcript Directory")
            open_dir_button.clicked.connect(lambda: os.startfile(self.transcript_directory))
            transcript_layout.addWidget(open_dir_button)

            transcript_window.setLayout(transcript_layout)
            transcript_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            transcript_window.setMinimumSize(400, 300)

            self.transcript_windows.append(transcript_window)
            transcript_window.show()

            QMessageBox.information(self, "Transcript Saved", f"Transcript saved to: {file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Transcription Error", f"Could not retrieve or save transcript: {str(e)}")

    def export_results(self):
        if not hasattr(self, 'video_results') or not self.video_results:
            QMessageBox.warning(self, "No Results", "No results to export. Please perform a search first.")
            return

        file_name, _ = QFileDialog.getSaveFileName(self, "Save CSV File", "", "CSV Files (*.csv)")
        if file_name:
            export_to_csv(self.video_results, file_name, self.use_api)
            QMessageBox.information(self, "Export Successful",
                                    f"Exported {len(self.video_results)} videos to {file_name}")

    def change_transcript_directory(self):
        new_directory = QFileDialog.getExistingDirectory(self, "Select Transcript Directory")
        if new_directory:
            self.transcript_directory = new_directory
            QMessageBox.information(self, "Directory Changed",
                                    f"Transcript directory changed to: {self.transcript_directory}")


def main():
    app = QApplication([])
    ex = YouTubeAnalyzer()
    ex.show()
    app.exec()


if __name__ == "__main__":
    main()
