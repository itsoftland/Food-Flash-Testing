from rest_framework import serializers
from vendors.models import ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = [
            'message_id',
            'sender',
            'message_text',
            'audio_file',
            'reply_to',
            'created_at',
        ]
