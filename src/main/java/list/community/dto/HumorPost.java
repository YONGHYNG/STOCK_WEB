package list.community.dto;

public class HumorPost {
    private String title;
    private String hits;
    private String likes;

    public HumorPost(String title, String hits, String likes) {
        this.title = title;
        this.hits = hits;
        this.likes = likes;
    }

    public String getTitle() {
        return title;
    }

    public String getHits() {
        return hits;
    }

    public String getLikes() {
        return likes;
    }
}

